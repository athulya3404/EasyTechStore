document.addEventListener("DOMContentLoaded", function() {
    const form = document.getElementById('apiProductForm');
    
    if (!form) return;
    
    form.addEventListener('submit', async function(e) {
        // 1. Stop the page from doing a standard form reload (prevents the '?' in the URL)
        e.preventDefault();
        
        // 2. Grab the CSRF token from the meta tag
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        if (!csrfMeta) {
            alert("Security error: CSRF token meta tag is missing from base.html.");
            return;
        }
        const csrfToken = csrfMeta.getAttribute('content');
        
        // 3. Build the FormData payload
        const formData = new FormData();
        formData.append('name', document.getElementById('name').value);
        formData.append('description', document.getElementById('description').value);
        formData.append('price', document.getElementById('price').value);
        formData.append('stock', document.getElementById('stock').value);
        formData.append('category', document.getElementById('category').value);
        
        const imageInput = document.getElementById('image');
        if (imageInput.files.length > 0) {
            formData.append('image', imageInput.files[0]);
        }
        
        try {
            // 4. Send asynchronous request to your DRF API
            const response = await fetch('/api/products/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                body: formData
            });
            
            if (response.ok) {
                const newProduct = await response.json();
                alert(`Success! Product "${newProduct.name}" was added.`);
                form.reset();
            } else {
                const errors = await response.json();
                console.error("Validation errors from server:", errors);
                
                // Friendly error alerting if Category ID doesn't exist
                if (errors.category) {
                    alert("Error: The Category ID you entered does not exist in the database. Please check your categories.");
                } else {
                    alert("Failed to add product. Check browser console (F12) for details.");
                }
            }
        } catch (error) {
            console.error("Network error:", error);
            alert("A network error occurred while trying to save the product.");
        }
    });
});