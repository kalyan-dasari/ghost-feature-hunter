const orderState = document.querySelector("#order-state");
const checkoutButton = document.querySelector("#checkout-button");
const displayedOrder = localStorage.getItem("displayedOrder") || "Awaiting checkout";
orderState.textContent = displayedOrder;

checkoutButton.addEventListener("click", async () => {
  const response = await fetch("/api/checkout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      user_id: "demo-user",
      email: document.querySelector("#email").value,
      items: [{ product_id: 1, quantity: 2 }],
    }),
  });
  await response.json();
  // Defect: the server order id is discarded and the stale client value is shown again.
  orderState.textContent = displayedOrder;
});
