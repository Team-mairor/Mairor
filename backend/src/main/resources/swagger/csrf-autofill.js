
// ---- Mairor: 로그인·내 계정 조회 응답의 csrfToken 을 이후 변경 요청의 X-CSRF-TOKEN 헤더에 자동으로 넣는다 (Swagger UI 전용)
(function () {
  var TOKEN_SOURCES = ['/v1/users/login', '/v1/users/me'];
  var SAFE_METHODS = ['GET', 'HEAD', 'OPTIONS'];
  var token = null;
  var originalFetch = window.fetch.bind(window);

  function pathOf(url) {
    try {
      return new URL(url, window.location.href).pathname;
    } catch (e) {
      return '';
    }
  }

  function endsWithAny(path, suffixes) {
    return suffixes.some(function (suffix) {
      return path.endsWith(suffix);
    });
  }

  window.fetch = function (input, init) {
    var request = new Request(input, init);
    var path = pathOf(request.url);
    var sameOrigin = new URL(request.url, window.location.href).origin === window.location.origin;
    // Authorize 에 직접 넣은 값이 있으면 그것을 존중한다
    if (sameOrigin && token && SAFE_METHODS.indexOf(request.method) < 0
        && !request.headers.has('X-CSRF-TOKEN')) {
      request.headers.set('X-CSRF-TOKEN', token);
    }
    return originalFetch(request).then(function (response) {
      if (!sameOrigin) {
        return response;
      }
      if (response.ok && endsWithAny(path, TOKEN_SOURCES)) {
        // 토큰을 저장한 뒤에 응답을 돌려줘서, 바로 다음 요청에도 토큰이 들어가게 한다
        return response.clone().json().then(function (body) {
          if (body && body.csrfToken) {
            token = body.csrfToken;
          }
        }).catch(function () {}).then(function () {
          return response;
        });
      }
      if (response.status === 401 || (response.ok && request.method !== 'GET'
          && (path.endsWith('/logout') || path.indexOf('/v1/users/me/sessions') >= 0))) {
        token = null;
      }
      return response;
    });
  };
})();
