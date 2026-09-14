/**
 * EasyTech Store - AI Chatbot Widget (Local Ollama + RAG)
 */

document.addEventListener("DOMContentLoaded", function () {
    const launcher = document.getElementById("easytech-chat-launcher");
    const panel = document.getElementById("easytech-chat-panel");
    const closeBtn = document.getElementById("chat-close-btn");
    const chatForm = document.getElementById("easytech-chat-form");
    const chatInput = document.getElementById("chat-input-text");
    const messagesContainer = document.getElementById("easytech-chat-messages");
    const suggestionChips = document.querySelectorAll(".quick-prompt-chip");

    if (!launcher || !panel) return;

    let historyLoaded = false;

    // Load Chat History from API
    async function loadChatHistory() {
        if (historyLoaded) return;
        try {
            const res = await fetch("/chatbot/api/history/");
            if (res.ok) {
                const data = await res.json();
                if (data.history && data.history.length > 0) {
                    messagesContainer.innerHTML = "";
                    data.history.forEach(item => {
                        if (item.sender === "user") {
                            appendUserMessage(item.message);
                        } else {
                            appendBotMessage(item.message, item.products || [], item.id, item.rating);
                        }
                    });
                }
                historyLoaded = true;
            }
        } catch (err) {
            console.warn("Could not load chat history:", err);
        }
    }

    // Toggle Chat Window
    launcher.addEventListener("click", function () {
        if (panel.style.display === "none" || !panel.style.display) {
            panel.style.display = "flex";
            panel.classList.add("chat-panel-animate-in");
            loadChatHistory();
            chatInput.focus();
        } else {
            panel.style.display = "none";
        }
    });

    closeBtn.addEventListener("click", function () {
        panel.style.display = "none";
    });

    // Handle Quick Suggestion Chips
    suggestionChips.forEach(chip => {
        chip.addEventListener("click", function () {
            const prompt = this.getAttribute("data-prompt");
            if (prompt) {
                chatInput.value = prompt;
                chatForm.dispatchEvent(new Event("submit"));
            }
        });
    });

    // Auto-scroll messages
    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function sanitizeUrl(url) {
        if (!url) return "#";
        const trimmed = String(url).trim();
        if (/^(\/|https?:\/\/)/i.test(trimmed)) {
            return encodeURI(trimmed);
        }
        return "#";
    }

    function safePurify(html) {
        if (window.DOMPurify && typeof window.DOMPurify.sanitize === "function") {
            return window.DOMPurify.sanitize(html, {
                ALLOWED_TAGS: ['b', 'i', 'em', 'strong', 'a', 'p', 'br', 'span', 'ul', 'ol', 'li', 'div', 'small', 'img', 'button'],
                ALLOWED_ATTR: ['href', 'title', 'class', 'style', 'target', 'src', 'alt', 'onerror', 'data-prompt', 'data-rating', 'data-message-id', 'type', 'aria-label', 'rel']
            });
        }
        return html;
    }

    // Append Message to UI
    function appendUserMessage(text) {
        const div = document.createElement("div");
        div.className = "chat-msg user-msg";
        div.innerHTML = safePurify(`
            <div class="msg-bubble">
                <p class="mb-0">${escapeHtml(text)}</p>
            </div>
        `);
        messagesContainer.appendChild(div);
        scrollToBottom();
    }

    function appendBotMessage(text, products = [], messageId = null, currentRating = null) {
        const div = document.createElement("div");
        div.className = "chat-msg bot-msg";

        let productsHtml = "";
        if (products && products.length > 0) {
            const categories = [...new Set(products.map(p => p.category).filter(Boolean))];
            let heading = "Recommended Gadgets:";
            if (categories.length === 1 && categories[0] !== "Uncategorized") {
                heading = `Recommended ${escapeHtml(categories[0])}:`;
            }
            productsHtml = `
                <div class="chat-product-recommendations mt-3">
                    <div class="recommendations-heading">${heading}</div>
                    <div class="recommendations-list">
                        ${products.map(p => `
                            <a href="${sanitizeUrl(p.url)}" class="rec-product-card" target="_blank" rel="noopener noreferrer">
                                ${p.image_url ? `<img src="${sanitizeUrl(p.image_url)}" alt="${escapeHtml(p.name)}" class="rec-img" onerror="this.style.display='none'">` : ''}
                                <div class="rec-details">
                                    <div class="d-flex align-items-center gap-1 flex-wrap mb-1">
                                        ${p.category && p.category !== 'Uncategorized' ? `<span class="badge bg-primary-subtle text-primary border border-primary-subtle px-1 py-0" style="font-size: 0.62rem;">${escapeHtml(p.category)}</span>` : ''}
                                        ${p.brand ? `<span class="badge bg-dark text-warning px-1 py-0" style="font-size: 0.62rem;">${escapeHtml(p.brand)}</span>` : ''}
                                    </div>
                                    <span class="rec-name">${escapeHtml(p.name)}</span>
                                    ${p.specs_summary && p.specs_summary.length > 0 ? `
                                        <div class="rec-specs text-muted" style="font-size: 0.68rem; line-height: 1.2; margin-top: 2px;">
                                            <i class="fa-solid fa-microchip me-1 opacity-75"></i>${escapeHtml(p.specs_summary.join(" • "))}
                                        </div>
                                    ` : ''}
                                    <div class="d-flex align-items-center justify-content-between mt-1">
                                        <span class="rec-price">₹${Number(p.price).toLocaleString()}</span>
                                        ${p.stock !== undefined ? `<small class="text-muted" style="font-size: 0.7rem;">${p.stock} in stock</small>` : ''}
                                    </div>
                                </div>
                                <i class="fa-solid fa-arrow-up-right-from-square rec-arrow"></i>
                            </a>
                        `).join("")}
                    </div>
                </div>
            `;
        }

        // Render Markdown-like bold and line breaks safely
        const formattedText = formatBotText(text);

        let feedbackHtml = "";
        if (messageId) {
            const upActive = currentRating === "thumbs_up";
            const downActive = currentRating === "thumbs_down";
            feedbackHtml = `
                <div class="chat-feedback-row" data-message-id="${messageId}">
                    <span class="feedback-label">Helpful?</span>
                    <button type="button" class="btn-chat-feedback ${upActive ? 'active text-success' : ''}" data-rating="thumbs_up" title="Helpful" aria-label="Helpful">
                        <i class="${upActive ? 'fa-solid' : 'fa-regular'} fa-thumbs-up"></i>
                    </button>
                    <button type="button" class="btn-chat-feedback ${downActive ? 'active text-danger' : ''}" data-rating="thumbs_down" title="Not helpful" aria-label="Not helpful">
                        <i class="${downActive ? 'fa-solid' : 'fa-regular'} fa-thumbs-down"></i>
                    </button>
                </div>
            `;
        }

        div.innerHTML = safePurify(`
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-bubble">
                <div class="bot-text">${formattedText}</div>
                ${productsHtml}
                ${feedbackHtml}
            </div>
        `);
        messagesContainer.appendChild(div);
        scrollToBottom();
    }

    function appendTypingIndicator() {
        const id = "typing-" + Date.now();
        const div = document.createElement("div");
        div.id = id;
        div.className = "chat-msg bot-msg chat-typing-indicator";
        div.innerHTML = `
            <div class="msg-avatar"><i class="fa-solid fa-robot"></i></div>
            <div class="msg-bubble typing-dots">
                <span></span><span></span><span></span>
            </div>
        `;
        messagesContainer.appendChild(div);
        scrollToBottom();
        return id;
    }

    function removeElement(id) {
        const el = document.getElementById(id);
        if (el) el.remove();
    }

    function escapeHtml(str) {
        const div = document.createElement("div");
        div.textContent = str;
        return div.innerHTML;
    }

    function formatBotText(str) {
        if (!str) return "";
        let safe = escapeHtml(str);
        // Replace bold **word** with <strong>word</strong>
        safe = safe.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        // Replace newlines with <br>
        safe = safe.replace(/\n/g, '<br>');
        return safe;
    }

    // Submit handler
    chatForm.addEventListener("submit", async function (e) {
        e.preventDefault();
        const query = chatInput.value.trim();
        if (!query) return;

        appendUserMessage(query);
        chatInput.value = "";
        chatInput.disabled = true;

        const typingId = appendTypingIndicator();

        try {
            const response = await fetch("/chatbot/api/chat/", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ message: query, top_k: 3 }),
            });

            removeElement(typingId);

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                appendBotMessage("⚠️ " + (errData.error || errData.reply || "Could not get a response from local AI. Please verify Ollama is running on your PC."));
            } else {
                const data = await response.json();
                appendBotMessage(data.reply || "I couldn't find an answer for that query.", data.products || [], data.message_id, null);
            }
        } catch (error) {
            removeElement(typingId);
            appendBotMessage("⚠️ Connection error reaching local AI service. Ensure Ollama is active on your machine.");
            console.error("Chat error:", error);
        } finally {
            chatInput.disabled = false;
            chatInput.focus();
        }
    });

    // Feedback rating click listener delegation
    messagesContainer.addEventListener("click", async function (e) {
        const btn = e.target.closest(".btn-chat-feedback");
        if (!btn) return;
        const row = btn.closest(".chat-feedback-row");
        if (!row) return;
        const messageId = row.getAttribute("data-message-id");
        const targetRating = btn.getAttribute("data-rating");
        if (!messageId || !targetRating) return;

        const isCurrentlyActive = btn.classList.contains("active");
        const newRating = isCurrentlyActive ? "clear" : targetRating;

        try {
            const res = await fetch("/chatbot/api/feedback/", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ message_id: parseInt(messageId, 10), rating: newRating }),
            });
            if (res.ok) {
                const allButtons = row.querySelectorAll(".btn-chat-feedback");
                allButtons.forEach(b => {
                    b.classList.remove("active", "text-success", "text-danger");
                    const icon = b.querySelector("i");
                    if (icon) {
                        icon.className = icon.className.replace("fa-solid", "fa-regular");
                    }
                });

                if (newRating !== "clear") {
                    btn.classList.add("active", newRating === "thumbs_up" ? "text-success" : "text-danger");
                    const icon = btn.querySelector("i");
                    if (icon) {
                        icon.className = icon.className.replace("fa-regular", "fa-solid");
                    }
                }
            }
        } catch (err) {
            console.warn("Could not save feedback:", err);
        }
    });
});
