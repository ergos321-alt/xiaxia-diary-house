document.querySelectorAll("textarea[maxlength]").forEach((textarea) => {
  const counter = document.querySelector(`[data-count-for="${textarea.id}"]`);
  if (!counter) return;
  const update = () => {
    counter.textContent = `${textarea.value.length} / ${textarea.maxLength}`;
  };
  textarea.addEventListener("input", update);
  update();
});

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector('button[type="submit"]');
    if (!button || button.dataset.submitting === "true") return;
    button.dataset.submitting = "true";
    button.setAttribute("aria-busy", "true");
  });
});

