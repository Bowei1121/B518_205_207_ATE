document.querySelectorAll("pre").forEach((block) => {
  const button = document.createElement("button");
  button.className = "copy-button";
  button.type = "button";
  button.textContent = "複製";
  button.setAttribute("aria-label", "複製指令");
  button.addEventListener("click", async () => {
    const text = block.querySelector("code")?.innerText || block.textContent;
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = "已複製";
      window.setTimeout(() => { button.textContent = "複製"; }, 1500);
    } catch (_) {
      button.textContent = "請手動選取";
    }
  });
  block.appendChild(button);
});
