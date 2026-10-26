// UV 마스크를 얼굴 메시에 입혀 알파 이미지로 그린다.
// 2D 캔버스로 삼각형마다 잘라 그리면 경계에 선이 생겨, 메시 전체를 WebGL 한 번에 그린다.

const VERTEX = `
attribute vec2 aPos;
attribute vec2 aUv;
attribute float aAlpha;
uniform vec2 uSize;
varying vec2 vUv;
varying float vAlpha;
void main() {
  vec2 clip = aPos / uSize * 2.0 - 1.0;
  gl_Position = vec4(clip.x, -clip.y, 0.0, 1.0);
  vUv = aUv;
  vAlpha = aAlpha;
}`;

const FRAGMENT = `
precision mediump float;
uniform sampler2D uMask;
varying vec2 vUv;
varying float vAlpha;
void main() {
  float a = texture2D(uMask, vUv).a * vAlpha;
  gl_FragColor = vec4(a, a, a, a);
}`;

function compile(gl: WebGLRenderingContext, type: number, source: string) {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(shader) ?? "셰이더 컴파일 실패");
  }
  return shader;
}

export class UvMaskGl {
  readonly canvas = document.createElement("canvas");
  private readonly gl: WebGLRenderingContext;
  private readonly program: WebGLProgram;
  private readonly shaders: WebGLShader[];
  private readonly posBuffer: WebGLBuffer;
  private readonly uvBuffer: WebGLBuffer;
  private readonly alphaBuffer: WebGLBuffer;
  // dispose에서 지울 수 있게 WeakMap 대신 Map을 쓴다. 마스크 이미지는 레이어 수만큼만 생긴다.
  private readonly textures = new Map<TexImageSource, WebGLTexture>();

  constructor() {
    const gl = this.canvas.getContext("webgl", { premultipliedAlpha: true, antialias: false });
    if (!gl) throw new Error("WebGL을 쓸 수 없습니다");
    this.gl = gl;

    const program = gl.createProgram()!;
    const shaders: WebGLShader[] = [];
    try {
      shaders.push(
        compile(gl, gl.VERTEX_SHADER, VERTEX),
        compile(gl, gl.FRAGMENT_SHADER, FRAGMENT),
      );
      for (const shader of shaders) gl.attachShader(program, shader);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
        throw new Error(gl.getProgramInfoLog(program) ?? "셰이더 연결 실패");
      }
    } catch (e) {
      // 다시 시도할 때마다 컨텍스트가 쌓이지 않도록 바로 놓는다.
      for (const shader of shaders) gl.deleteShader(shader);
      gl.deleteProgram(program);
      gl.getExtension("WEBGL_lose_context")?.loseContext();
      throw e;
    }
    this.shaders = shaders;
    this.program = program;
    this.posBuffer = gl.createBuffer()!;
    this.uvBuffer = gl.createBuffer()!;
    this.alphaBuffer = gl.createBuffer()!;
  }

  /** GPU 리셋 등으로 컨텍스트가 끊기면 다시 만들어야 한다. */
  get lost() {
    return this.gl.isContextLost();
  }

  /**
   * GPU 자원과 컨텍스트를 놓는다. 브라우저는 WebGL 컨텍스트 수에 한도가 있어,
   * 놓지 않으면 다시 마운트할 때마다 쌓이다가 얼굴 추적기의 컨텍스트까지 끊긴다.
   */
  dispose() {
    const gl = this.gl;
    for (const texture of this.textures.values()) gl.deleteTexture(texture);
    this.textures.clear();
    for (const buffer of [this.posBuffer, this.uvBuffer, this.alphaBuffer]) gl.deleteBuffer(buffer);
    for (const shader of this.shaders) gl.deleteShader(shader);
    gl.deleteProgram(this.program);
    gl.getExtension("WEBGL_lose_context")?.loseContext();
    this.canvas.width = this.canvas.height = 0;
  }

  private texture(image: TexImageSource) {
    const gl = this.gl;
    let texture = this.textures.get(image);
    if (!texture) {
      texture = gl.createTexture()!;
      gl.bindTexture(gl.TEXTURE_2D, texture);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, image);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      this.textures.set(image, texture);
    }
    return texture;
  }

  /**
   * 삼각형들을 그린다.
   * @param positions 꼭짓점 위치 (기기 픽셀, 삼각형마다 3개)
   * @param uvs 꼭짓점 UV (0~1, 원점 왼쪽 위)
   * @param alphas 꼭짓점별 진하기 배율 (0~1)
   */
  draw(
    image: TexImageSource,
    positions: Float32Array,
    uvs: Float32Array,
    alphas: Float32Array,
    width: number,
    height: number,
  ) {
    const gl = this.gl;
    if (this.canvas.width !== width || this.canvas.height !== height) {
      this.canvas.width = width;
      this.canvas.height = height;
    }
    gl.viewport(0, 0, width, height);
    gl.clearColor(0, 0, 0, 0);
    gl.clear(gl.COLOR_BUFFER_BIT);
    gl.useProgram(this.program);

    const bind = (buffer: WebGLBuffer, data: Float32Array, name: string, size: number) => {
      const location = gl.getAttribLocation(this.program, name);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, data, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, size, gl.FLOAT, false, 0, 0);
    };
    bind(this.posBuffer, positions, "aPos", 2);
    bind(this.uvBuffer, uvs, "aUv", 2);
    bind(this.alphaBuffer, alphas, "aAlpha", 1);

    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, this.texture(image));
    gl.uniform1i(gl.getUniformLocation(this.program, "uMask"), 0);
    gl.uniform2f(gl.getUniformLocation(this.program, "uSize"), width, height);
    gl.drawArrays(gl.TRIANGLES, 0, positions.length / 2);
  }
}
