/** Material-style ripple on every enabled button, from the point that was pressed. */
export function installRipple() {
  document.addEventListener("pointerdown", (e) => {
    const button = (e.target as HTMLElement).closest("button");
    if (!button || button.disabled || button.classList.contains("no-ripple")) return;
    const rect = button.getBoundingClientRect();
    const size = Math.max(rect.width, rect.height) * 2;
    const ripple = document.createElement("span");
    ripple.className = "ripple";
    ripple.style.width = ripple.style.height = `${size}px`;
    ripple.style.left = `${e.clientX - rect.left - size / 2}px`;
    ripple.style.top = `${e.clientY - rect.top - size / 2}px`;
    button.appendChild(ripple);
    ripple.addEventListener("animationend", () => ripple.remove());
  });
}
