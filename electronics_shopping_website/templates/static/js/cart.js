// ============================================================
// PRODUCT DETAIL PAGE
// ============================================================

// Increase product quantity
function incrementQty() {
    const input = document.getElementById("productQty");

    if (input) {
        const currentValue = parseInt(input.value, 10) || 1;
        input.value = currentValue + 1;
    }
}


// Decrease product quantity
// Minimum quantity is 1
function decrementQty() {
    const input = document.getElementById("productQty");

    if (input) {
        const currentValue = parseInt(input.value, 10) || 1;

        if (currentValue > 1) {
            input.value = currentValue - 1;
        }
    }
}


// ============================================================
// ADD PRODUCT TO CART
// ============================================================

async function addCurrentProductToCart(productId) {
    const qtyInput = document.getElementById("productQty");

    // Get quantity from input, default to 1
    const quantity = qtyInput
        ? parseInt(qtyInput.value, 10) || 1
        : 1;

    // Get CSRF token
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta
        ? csrfMeta.getAttribute("content")
        : "";

    try {
        const response = await fetch("/api/cart/add_item/", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            },
            body: JSON.stringify({
                product_id: productId,
                quantity: quantity
            })
        });

        if (response.ok) {
            alert("Product added to your cart successfully!");

        } else if (response.status === 403) {
            alert("Please log in to add items to your cart.");
            window.location.href = "/accounts/login/";

        } else {
            const data = await response.json().catch(() => ({}));

            alert(
                "Failed to add item to cart: " +
                (data.error || "Unknown error")
            );
        }

    } catch (error) {
        console.error("Add to cart error:", error);
        alert("An error occurred while connecting to the server.");
    }
}


// ============================================================
// UPDATE CART ITEM QUANTITY
// ============================================================

async function updateCartItem(itemId, newQuantity) {

    // If quantity becomes 0, remove the item
    if (newQuantity < 1) {
        await removeCartItem(itemId);
        return;
    }

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta
        ? csrfMeta.getAttribute("content")
        : "";

    try {
        const response = await fetch(
            `/api/cart/update_quantity/${itemId}/`,
            {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                },
                body: JSON.stringify({
                    quantity: newQuantity
                })
            }
        );

        if (response.ok) {

            // Reload the cart page so that
            // subtotal and total are updated
            window.location.reload();

        } else {
            const data = await response.json().catch(() => ({}));

            alert(
                "Failed to update item quantity: " +
                (data.error || "Unknown error")
            );
        }

    } catch (error) {
        console.error("Update cart error:", error);
        alert("An error occurred while updating the cart.");
    }
}


// ============================================================
// REMOVE ITEM FROM CART
// ============================================================

async function removeCartItem(itemId) {

    // Ask the user for confirmation
    const confirmed = confirm(
        "Are you sure you want to remove this item?"
    );

    if (!confirmed) {
        return;
    }

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta
        ? csrfMeta.getAttribute("content")
        : "";

    try {
        const response = await fetch(
            `/api/cart/remove_item/${itemId}/`,
            {
                method: "DELETE",
                headers: {
                    "Content-Type": "application/json",
                    "X-CSRFToken": csrfToken
                }
            }
        );

        if (response.ok) {

            // Reload the cart page
            // so the removed item disappears
            window.location.reload();

        } else {
            const data = await response.json().catch(() => ({}));

            alert(
                "Failed to remove item: " +
                (data.error || "Unknown error")
            );
        }

    } catch (error) {
        console.error("Remove cart item error:", error);
        alert("An error occurred while removing the item.");
    }
}


// ============================================================
// CHECKOUT / PLACE ORDER
// ============================================================

document.addEventListener("DOMContentLoaded", function () {

    const confirmPayBtn =
        document.getElementById("confirmPayBtn");

    // Only run this code if the checkout button
    // exists on the current page
    if (!confirmPayBtn) {
        return;
    }

    confirmPayBtn.addEventListener("click", async function () {

        const addressInput =
            document.getElementById("shippingAddress");

        // ----------------------------------------------------
        // Validate shipping address
        // ----------------------------------------------------

        if (!addressInput || !addressInput.value.trim()) {

            alert("Please enter a valid shipping address.");

            if (addressInput) {
                addressInput.focus();
            }

            return;
        }


        // ----------------------------------------------------
        // Disable button to prevent double-clicking
        // ----------------------------------------------------

        confirmPayBtn.disabled = true;
        confirmPayBtn.textContent = "Processing...";


        // ----------------------------------------------------
        // Get CSRF token
        // ----------------------------------------------------

        const csrfMeta =
            document.querySelector('meta[name="csrf-token"]');

        const csrfToken = csrfMeta
            ? csrfMeta.getAttribute("content")
            : "";


        try {

            // ------------------------------------------------
            // Send order request to Django API
            // ------------------------------------------------

            const response = await fetch(
                "/api/orders/place_order/",
                {
                    method: "POST",

                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },

                    body: JSON.stringify({
                        shipping_address:
                            addressInput.value.trim()
                    })
                }
            );


            // Try to read JSON response
            const data = await response.json().catch(() => ({}));


            // ------------------------------------------------
            // Order successfully placed
            // ------------------------------------------------

            if (response.ok) {

                alert(
                    "Order placed successfully! " +
                    "Your order ID is: #" +
                    data.order_id
                );

                // Redirect to homepage
                window.location.href = "/";

            }

            // ------------------------------------------------
            // Order failed
            // ------------------------------------------------

            else {

                alert(
                    "Failed to place order: " +
                    (data.error || "Unknown error")
                );

                // Enable button again
                confirmPayBtn.disabled = false;
                confirmPayBtn.textContent = "Confirm & Pay";
            }

        } catch (error) {

            console.error("Checkout error:", error);

            alert(
                "An error occurred during checkout."
            );

            // Enable button again
            confirmPayBtn.disabled = false;
            confirmPayBtn.textContent = "Confirm & Pay";
        }

    });

});