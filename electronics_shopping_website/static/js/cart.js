// ============================================================
// PRODUCT DETAIL PAGE QUANTITY CONTROLS
// ============================================================

function incrementQty() {
    const input = document.getElementById("productQty");
    if (input) {
        const currentValue = parseInt(input.value, 10) || 1;
        input.value = currentValue + 1;
    }
}

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
// TOAST NOTIFICATION & AUTH REDIRECT HELPERS
// ============================================================

function showToast(message, type = "info") {
    let container = document.getElementById("easytech-toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "easytech-toast-container";
        container.className = "toast-container position-fixed bottom-0 end-0 p-3";
        container.style.zIndex = "1090";
        document.body.appendChild(container);
    }

    const toastId = "toast_" + Math.random().toString(36).substring(2, 9);
    const bgClass = (type === "success") ? "bg-success text-white" : ((type === "danger" || type === "error") ? "bg-danger text-white" : "bg-dark text-white");
    const icon = (type === "success") ? "✓" : ((type === "danger" || type === "error") ? "⚠" : "ℹ");

    const toastEl = document.createElement("div");
    toastEl.id = toastId;
    toastEl.className = `toast align-items-center ${bgClass} border-0 shadow-lg rounded-3 mb-2`;
    toastEl.setAttribute("role", "alert");
    toastEl.setAttribute("aria-live", "assertive");
    toastEl.setAttribute("aria-atomic", "true");
    toastEl.innerHTML = `
        <div class="d-flex align-items-center">
            <div class="toast-body d-flex align-items-center gap-2 py-2 px-3">
                <span class="fs-6 fw-bold">${icon}</span>
                <span>${message}</span>
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    container.appendChild(toastEl);

    if (window.bootstrap && window.bootstrap.Toast) {
        const bsToast = new window.bootstrap.Toast(toastEl, { delay: 3500 });
        bsToast.show();
        toastEl.addEventListener("hidden.bs.toast", () => toastEl.remove());
    } else {
        toastEl.classList.add("show");
        setTimeout(() => toastEl.remove(), 3500);
    }
}

function handleUnauthenticated(message = "Please log in to continue.") {
    showToast(message, "danger");
    const currentPath = encodeURIComponent(window.location.pathname + window.location.search);
    setTimeout(() => {
        window.location.href = `/accounts/login/?next=${currentPath}`;
    }, 1000);
}

// ============================================================
// ADD PRODUCT TO CART & BUY NOW (GENERIC HELPER)
// ============================================================

async function addProductToCart(productId, quantity = 1, redirectCheckout = false) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

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
            const data = await response.json().catch(() => ({}));
            if (redirectCheckout) {
                const targetItemId = data.cart_item_id || data.added_item_id || (data.items && data.items.find(i => i.product && i.product.id === parseInt(productId, 10))?.id);
                if (targetItemId) {
                    window.location.href = `/orders/checkout/?items=${targetItemId}`;
                } else {
                    window.location.href = `/orders/checkout/?product_id=${productId}&quantity=${quantity}`;
                }
            } else {
                showToast("Product added to your cart successfully!", "success");
                if (window.location.pathname.includes("/cart/")) {
                    setTimeout(() => window.location.reload(), 500);
                }
            }
        } else if (response.status === 403 || response.status === 401) {
            handleUnauthenticated("Please log in to add items to your cart.");
        } else {
            const data = await response.json().catch(() => ({}));
            showToast("Could not add product: " + (data.error || "Unknown error"), "danger");
        }
    } catch (error) {
        console.error("Cart error:", error);
        showToast("An error occurred while connecting to the server.", "danger");
    }
}

// Alias for global inline button onclick handlers
window.addToCart = addProductToCart;

// For product detail page with custom quantity input
async function addCurrentProductToCart(productId, redirectCheckout = false) {
    const qtyInput = document.getElementById("productQty");
    const quantity = qtyInput ? parseInt(qtyInput.value, 10) || 1 : 1;
    await addProductToCart(productId, quantity, redirectCheckout);
}

// ============================================================
// WISHLIST TOGGLE (AJAX)
// ============================================================

async function toggleWishlist(productId, buttonElement) {
    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

    try {
        const response = await fetch(`/api/wishlist/toggle/${productId}/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            }
        });

        if (response.ok) {
            const data = await response.json();
            if (buttonElement) {
                if (data.added) {
                    buttonElement.classList.remove("text-muted");
                    buttonElement.classList.add("text-danger");
                    buttonElement.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" class="bi bi-heart-fill" viewBox="0 0 16 16">
                            <path fill-rule="evenodd" d="M8 1.314C12.438-3.248 23.534 4.735 8 15-7.534 4.736 3.562-3.248 8 1.314z"/>
                        </svg>
                    `;
                } else {
                    buttonElement.classList.remove("text-danger");
                    buttonElement.classList.add("text-muted");
                    buttonElement.innerHTML = `
                        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" class="bi bi-heart" viewBox="0 0 16 16">
                            <path d="m8 2.748-.717-.737C5.6.281 2.514.878 1.4 3.053c-.523 1.023-.641 2.5.314 4.385.92 1.815 2.834 3.989 6.286 6.357 3.452-2.368 5.365-4.542 6.286-6.357.955-1.886.838-3.362.314-4.385C13.486.878 10.4.28 8.717 2.01L8 2.748zM8 15C-7.333 4.868 3.279-3.04 7.824 1.143c.06.055.119.112.176.171a3.12 3.12 0 0 1 .176-.17C12.72-3.042 23.333 4.867 8 15z"/>
                        </svg>
                    `;
                    const cardCol = document.getElementById(`wishlist-item-${productId}`);
                    if (cardCol) {
                        cardCol.remove();
                    }
                }
            }
        } else if (response.status === 403 || response.status === 401) {
            handleUnauthenticated("Please log in to save items to your wishlist.");
        } else {
            const data = await response.json().catch(() => ({}));
            showToast(data.message || "Failed to update wishlist.", "danger");
        }
    } catch (error) {
        console.error("Wishlist error:", error);
        showToast("An error occurred while connecting to the server.", "danger");
    }
}

// ============================================================
// UPDATE CART ITEM QUANTITY
// ============================================================

async function updateCartItem(itemId, newQuantity) {
    if (newQuantity < 1) {
        await removeCartItem(itemId);
        return;
    }

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

    try {
        const response = await fetch(`/api/cart/update_quantity/${itemId}/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            },
            body: JSON.stringify({ quantity: newQuantity })
        });

        if (response.ok) {
            window.location.reload();
        } else {
            const data = await response.json().catch(() => ({}));
            alert("Failed to update item quantity: " + (data.error || "Unknown error"));
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
    const confirmed = confirm("Are you sure you want to remove this item from your cart?");
    if (!confirmed) return;

    const csrfMeta = document.querySelector('meta[name="csrf-token"]');
    const csrfToken = csrfMeta ? csrfMeta.getAttribute("content") : "";

    try {
        const response = await fetch(`/api/cart/remove_item/${itemId}/`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": csrfToken
            }
        });

        if (response.ok) {
            window.location.reload();
        } else {
            const data = await response.json().catch(() => ({}));
            alert("Failed to remove item: " + (data.error || "Unknown error"));
        }
    } catch (error) {
        console.error("Remove cart item error:", error);
        alert("An error occurred while removing the item.");
    }
}

// ============================================================
// SELECTIVE CART RECALCULATION HELPER
// ============================================================

function recalculateSelectiveCart() {
    const checkboxes = document.querySelectorAll(".cart-item-checkbox");
    if (!checkboxes.length) return;

    let selectedCount = 0;
    let selectedTotal = 0.0;
    const selectedIds = [];

    checkboxes.forEach(cb => {
        if (cb.checked) {
            selectedCount += 1;
            const subtotal = parseFloat(cb.getAttribute("data-subtotal")) || 0.0;
            selectedTotal += subtotal;
            selectedIds.push(cb.getAttribute("data-item-id"));
        }
    });

    const countElem = document.getElementById("selectedItemCount");
    const subtotalElem = document.getElementById("cartSubtotal");
    const totalElem = document.getElementById("cartTotal");
    const checkoutBtn = document.getElementById("proceedToCheckoutBtn");
    const noSelectionAlert = document.getElementById("noSelectionAlert");

    if (countElem) countElem.textContent = selectedCount;
    if (subtotalElem) subtotalElem.textContent = "₹" + selectedTotal.toFixed(2);
    if (totalElem) totalElem.textContent = "₹" + selectedTotal.toFixed(2);

    if (checkoutBtn) {
        if (selectedCount > 0) {
            checkoutBtn.classList.remove("disabled", "btn-secondary");
            checkoutBtn.classList.add("btn-primary");
            checkoutBtn.href = `/orders/checkout/?items=${selectedIds.join(",")}`;
            if (noSelectionAlert) noSelectionAlert.classList.add("d-none");
        } else {
            checkoutBtn.classList.remove("btn-primary");
            checkoutBtn.classList.add("disabled", "btn-secondary");
            checkoutBtn.removeAttribute("href");
            if (noSelectionAlert) noSelectionAlert.classList.remove("d-none");
        }
    }
}

// ============================================================
// DOM EVENT LISTENERS (CART, BUY NOW, WISHLIST & CHECKOUT)
// ============================================================

document.addEventListener("DOMContentLoaded", function () {

    // 1. Initial Selective Cart Calculation & Checkbox Listeners
    const selectAllCheckbox = document.getElementById("selectAllCartItems");
    const itemCheckboxes = document.querySelectorAll(".cart-item-checkbox");

    if (selectAllCheckbox) {
        selectAllCheckbox.addEventListener("change", function () {
            const isChecked = this.checked;
            itemCheckboxes.forEach(cb => {
                cb.checked = isChecked;
            });
            recalculateSelectiveCart();
        });
    }

    itemCheckboxes.forEach(cb => {
        cb.addEventListener("change", function () {
            if (selectAllCheckbox) {
                const allChecked = Array.from(itemCheckboxes).every(i => i.checked);
                selectAllCheckbox.checked = allChecked;
            }
            recalculateSelectiveCart();
        });
    });

    recalculateSelectiveCart();

    // 2. Global Click Listeners
    document.addEventListener("click", function (e) {
        // Wishlist button click
        const wishlistBtn = e.target.closest(".wishlist-toggle-btn");
        if (wishlistBtn) {
            e.preventDefault();
            const productId = wishlistBtn.getAttribute("data-product-id");
            if (productId) {
                toggleWishlist(productId, wishlistBtn);
            }
            return;
        }

        // Add to Cart button click
        const cartBtn = e.target.closest(".add-to-cart-btn");
        if (cartBtn) {
            e.preventDefault();
            const productId = cartBtn.getAttribute("data-product-id");
            if (productId) {
                addProductToCart(productId, 1, false);
            }
            return;
        }

        // Buy Now button click
        const buyNowBtn = e.target.closest(".buy-now-btn");
        if (buyNowBtn) {
            e.preventDefault();
            const productId = buyNowBtn.getAttribute("data-product-id");
            if (productId) {
                addProductToCart(productId, 1, true);
            }
            return;
        }

        // Update Cart Quantity button click (+ or -)
        const updateBtn = e.target.closest(".update-cart-btn");
        if (updateBtn) {
            e.preventDefault();
            const itemId = updateBtn.getAttribute("data-item-id");
            const newQty = parseInt(updateBtn.getAttribute("data-new-quantity"), 10);
            if (itemId && !isNaN(newQty)) {
                updateCartItem(itemId, newQty);
            }
            return;
        }

        // Remove Cart Item button click
        const removeBtn = e.target.closest(".remove-cart-btn");
        if (removeBtn) {
            e.preventDefault();
            const itemId = removeBtn.getAttribute("data-item-id");
            if (itemId) {
                removeCartItem(itemId);
            }
            return;
        }
    });

    // 3. Checkout Button Listener
    const confirmPayBtn = document.getElementById("confirmPayBtn");
    if (confirmPayBtn) {
        confirmPayBtn.addEventListener("click", async function () {
            const addressInput = document.getElementById("shippingAddress");
            const alertBox = document.getElementById("checkoutAlert");
            const selectedPayment = document.querySelector('input[name="paymentMethod"]:checked');
            const selectedItemIdsInput = document.getElementById("selectedItemIdsInput");

            const showError = (msg) => {
                if (alertBox) {
                    alertBox.textContent = msg;
                    alertBox.classList.remove("d-none");
                } else {
                    alert(msg);
                }
            };

            if (!addressInput || !addressInput.value.trim()) {
                showError("Please enter a valid shipping address.");
                if (addressInput) addressInput.focus();
                return;
            }

            confirmPayBtn.disabled = true;
            const originalBtnHtml = confirmPayBtn.innerHTML;
            confirmPayBtn.innerHTML = `
                <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                Connecting to Payment Gateway...
            `;
            if (alertBox) alertBox.classList.add("d-none");

            function getCsrfToken() {
                const csrfMeta = document.querySelector('meta[name="csrf-token"]');
                if (csrfMeta && csrfMeta.getAttribute("content")) {
                    return csrfMeta.getAttribute("content");
                }
                const inputToken = document.querySelector('[name="csrfmiddlewaretoken"]');
                if (inputToken && inputToken.value) {
                    return inputToken.value;
                }
                if (document.cookie && document.cookie !== '') {
                    const cookies = document.cookie.split(';');
                    for (let i = 0; i < cookies.length; i++) {
                        const cookie = cookies[i].trim();
                        if (cookie.startsWith('csrftoken=')) {
                            return decodeURIComponent(cookie.substring(10));
                        }
                    }
                }
                return "";
            }

            const csrfToken = getCsrfToken();

            let selectedItemIds = [];
            if (selectedItemIdsInput && selectedItemIdsInput.value) {
                try {
                    selectedItemIds = JSON.parse(selectedItemIdsInput.value);
                } catch(e) {
                    selectedItemIds = selectedItemIdsInput.value.split(",").map(Number).filter(Boolean);
                }
            }

            try {
                const response = await fetch("/api/orders/place_order/", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "X-CSRFToken": csrfToken
                    },
                    body: JSON.stringify({
                        shipping_address: addressInput.value.trim(),
                        payment_method: selectedPayment ? selectedPayment.value : "Sandbox",
                        selected_item_ids: selectedItemIds
                    })
                });

                let data = {};
                try {
                    data = await response.json();
                } catch (jsonErr) {
                    data = {};
                }

                if (response.ok && data.success) {
                    window.location.replace(data.redirect_url || "/orders/my-orders/");
                } else {
                    // Fallback to native form submission so order placement never fails
                    const checkoutForm = document.getElementById("checkoutForm");
                    if (checkoutForm) {
                        checkoutForm.submit();
                        return;
                    }
                    showError("Failed to place order: " + (data.error || "Please refresh and try again."));
                    confirmPayBtn.disabled = false;
                    confirmPayBtn.innerHTML = originalBtnHtml;
                }
            } catch (error) {
                console.error("Checkout error:", error);
                const checkoutForm = document.getElementById("checkoutForm");
                if (checkoutForm) {
                    checkoutForm.submit();
                    return;
                }
                showError("An error occurred while connecting to the server.");
                confirmPayBtn.disabled = false;
                confirmPayBtn.innerHTML = originalBtnHtml;
            }
        });
    }
});
