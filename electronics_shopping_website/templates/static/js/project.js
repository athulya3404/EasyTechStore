document.addEventListener("DOMContentLoaded", function() {
    const form = document.getElementById('apiProductForm');
    
    if (!form) {
        console.error("Could not find 'apiProductForm' on this page!");
        return;
    }
    
    form.addEventListener('submit', async function(e) {
        // THIS LINE IS CRITICAL: It stops the page from reloading and adding the '?' to the URL
        e.preventDefault();
        
        const csrfMeta = document.querySelector('meta[name="csrf-token"]');
        if (!csrfMeta) {
            alert("CSRF token meta tag is missing from base.html!");
            return;
        }
        const csrfToken = csrfMeta.getAttribute('content');
        
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
            const response = await fetch('/api/products/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': csrfToken
                },
                body: formData
            });
            
            if (response.ok) {
                const newProduct = await response.json();
                alert(`Success! ${newProduct.name} was added.`);
                form.reset();
            } else {
                const errors = await response.json();
                console.error("Validation errors from server:", errors);
                alert("Failed to add product. Check the browser console (F12) for details.");
            }
        } catch (error) {
            console.error("Network error:", error);
            alert("A network error occurred.");
        }
    });
});