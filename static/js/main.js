document.querySelectorAll(".candidate-card").forEach((card) => {
    card.addEventListener("click", () => {
        const input = card.querySelector("input");
        if (input) input.checked = true;
    });
});
