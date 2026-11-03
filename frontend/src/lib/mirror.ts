/** 미러필름 모드 저장 키. 서버 컴포넌트(app/layout.tsx)도 읽으므로 "use client" 파일 밖에 둔다 */
export const MIRROR_KEY = "mairor-mirror";

/**
 * 저장된 미러필름 모드를 그리기 전에 붙여 깜빡임을 막는 첫 화면 스크립트.
 * 브라우저 상단바 색(theme-color)도 검정으로 바꿔, 흰 상단바가 필름 위로 비치지 않게 한다
 */
export const MIRROR_SCRIPT = `try{if(localStorage.getItem("${MIRROR_KEY}")==="1"){document.documentElement.classList.add("mirror");var m=document.querySelector("meta[name=theme-color]");m&&m.setAttribute("content","#000000")}}catch(e){}`;

/** 지금 미러필름 모드인지 */
export const isMirror = () => document.documentElement.classList.contains("mirror");

/** 미러필름 모드를 켜고 끈다. 상단바 색도 함께 바꾼다 */
export function setMirror(on: boolean) {
  document.documentElement.classList.toggle("mirror", on);
  document
    .querySelector("meta[name=theme-color]")
    ?.setAttribute("content", on ? "#000000" : "#ffffff");
}
