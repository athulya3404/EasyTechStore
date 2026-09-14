import os
import re
import logging
from typing import List, Dict, Any, Optional

from django.conf import settings
from django.db.models import Q

from category.models import Category
from products.models import Product, Brand

logger = logging.getLogger(__name__)


# ============================================================
# SETTINGS
# ============================================================

OLLAMA_BASE_URL = getattr(
    settings,
    "OLLAMA_BASE_URL",
    "http://host.docker.internal:11434/v1",
)

OLLAMA_MODEL = getattr(
    settings,
    "OLLAMA_MODEL",
    "llama3.2",
)

OLLAMA_FALLBACK_MODEL = getattr(
    settings,
    "OLLAMA_FALLBACK_MODEL",
    "qwen2.5:7b",
)

OLLAMA_TIMEOUT = float(getattr(
    settings,
    "OLLAMA_TIMEOUT",
    8.0,
))

# Groq Cloud Settings
GROQ_API_KEY = getattr(settings, "GROQ_API_KEY", "")
LLM_PROVIDER = getattr(settings, "LLM_PROVIDER", "groq" if GROQ_API_KEY else "ollama").lower()
GROQ_BASE_URL = getattr(settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1")
GROQ_MODEL = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_FALLBACK_MODEL = getattr(settings, "GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b")
GROQ_TIMEOUT = float(getattr(settings, "GROQ_TIMEOUT", 15.0))


def get_llm_client_and_models(timeout_override: Optional[float] = None):
    """
    Returns (client, primary_model, fallback_model) dynamically
    based on active provider (Groq Cloud API or Local Ollama).
    """
    from openai import OpenAI
    active_provider = getattr(settings, "LLM_PROVIDER", "groq" if getattr(settings, "GROQ_API_KEY", "") else "ollama").lower()
    groq_key = getattr(settings, "GROQ_API_KEY", "")

    if (active_provider == "groq" or groq_key) and groq_key.strip():
        base_url = getattr(settings, "GROQ_BASE_URL", "https://api.groq.com/openai/v1")
        model = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b")
        fallback = getattr(settings, "GROQ_FALLBACK_MODEL", "qwen/qwen3.8-27b")
        timeout = timeout_override or float(getattr(settings, "GROQ_TIMEOUT", 15.0))
        client = OpenAI(base_url=base_url, api_key=groq_key.strip(), timeout=timeout)
        return client, model, fallback
    else:
        base_url = getattr(settings, "OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1")
        model = getattr(settings, "OLLAMA_MODEL", "llama3.2")
        fallback = getattr(settings, "OLLAMA_FALLBACK_MODEL", "qwen2.5:7b")
        timeout = timeout_override or float(getattr(settings, "OLLAMA_TIMEOUT", 8.0))
        client = OpenAI(base_url=base_url, api_key="ollama", timeout=timeout)
        return client, model, fallback

CHROMA_PERSIST_DIR = getattr(
    settings,
    "CHROMA_PERSIST_DIR",
    "/app/data/chroma_db",
)


_chroma_client = None
_collection = None


# ============================================================
# CHROMADB
# ============================================================

def get_chroma_collection():
    """Create ChromaDB collection only when required."""
    global _chroma_client, _collection

    if _collection is not None:
        return _collection

    try:
        import chromadb

        os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)

        _chroma_client = chromadb.PersistentClient(
            path=CHROMA_PERSIST_DIR
        )

        _collection = _chroma_client.get_or_create_collection(
            name="easytech_products",
            metadata={
                "description": (
                    "EasyTech Store product embeddings for "
                    "semantic product search"
                )
            },
        )

        return _collection

    except Exception as exc:
        logger.warning(
            "Could not initialize ChromaDB: %s",
            exc,
        )
        return None


# ============================================================
# PRODUCT SERIALIZATION
# ============================================================

def product_to_dict(product: Product) -> Dict[str, Any]:
    """
    Convert Django Product object into a consistent dictionary.
    """
    category = (
        product.category.name
        if product.category
        else "Uncategorized"
    )

    brand = (
        product.brand.name
        if product.brand
        else "Generic"
    )

    try:
        product_url = product.get_absolute_url()
    except Exception:
        product_url = f"/products/{product.slug or product.id}/"

    image_url = (
        product.image.url
        if getattr(product, "image", None)
        else "/static/images/placeholder.png"
    )

    specs = product.specifications if isinstance(product.specifications, dict) else {}
    specs_list = []
    if isinstance(specs, dict):
        for k, v in list(specs.items())[:3]:
            if v:
                specs_list.append(f"{k}: {v}")
            else:
                specs_list.append(str(k))
    elif isinstance(product.specifications, str) and product.specifications:
        specs_list = [s.strip() for s in product.specifications.split(";") if s.strip()][:3]

    return {
        "product_id": product.id,
        "name": product.name,
        "price": float(product.price),
        "category": category,
        "brand": brand,
        "url": product_url,
        "stock": product.stock,
        "image_url": image_url,
        "description": product.description or "",
        "specifications": specs,
        "specs_summary": specs_list,
    }


# ============================================================
# PRODUCT INDEXING
# ============================================================

def index_products(batch_size: int = 100) -> Dict[str, Any]:
    """
    Index all active products into ChromaDB.
    """
    collection = get_chroma_collection()

    products = (
        Product.objects
        .filter(is_active=True)
        .select_related("category", "brand")
    )

    total = products.count()

    if total == 0:
        return {
            "status": "empty",
            "indexed": 0,
        }

    if collection is None:
        return {
            "status": "chroma_unavailable",
            "indexed": 0,
        }

    documents = []
    metadatas = []
    ids = []

    for product in products:
        data = product_to_dict(product)

        document = (
            f"Product: {data['name']}\n"
            f"Brand: {data['brand']}\n"
            f"Category: {data['category']}\n"
            f"Price: ₹{data['price']}\n"
            f"Stock: {data['stock']} units\n"
            f"Description: {data['description']}\n"
            f"Specifications: {data['specifications']}"
        )

        documents.append(document)

        metadatas.append({
            "product_id": data["product_id"],
            "name": data["name"],
            "price": data["price"],
            "category": data["category"],
            "brand": data["brand"],
            "url": data["url"],
            "stock": data["stock"],
            "image_url": data["image_url"],
        })

        ids.append(f"prod_{product.id}")

        if len(documents) >= batch_size:
            collection.upsert(
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
            documents = []
            metadatas = []
            ids = []

    if documents:
        collection.upsert(
            documents=documents,
            metadatas=metadatas,
            ids=ids,
        )

    logger.info(
        "Successfully indexed %s products in ChromaDB.",
        total,
    )

    return {
        "status": "success",
        "indexed": total,
    }


def upsert_single_product(product: Product) -> bool:
    """Upsert a single product vector into ChromaDB collection in real time."""
    try:
        collection = get_chroma_collection()
        if collection is None:
            return False

        if not getattr(product, "is_active", True):
            # If deactivated, remove from vector collection
            delete_single_product(product.id)
            return True

        data = product_to_dict(product)
        document = (
            f"Product: {data['name']}\n"
            f"Brand: {data['brand']}\n"
            f"Category: {data['category']}\n"
            f"Price: ₹{data['price']}\n"
            f"Stock: {data['stock']} units\n"
            f"Description: {data['description']}\n"
            f"Specifications: {data['specifications']}"
        )
        metadata = {
            "product_id": data["product_id"],
            "name": data["name"],
            "price": data["price"],
            "category": data["category"],
            "brand": data["brand"],
            "url": data["url"],
            "stock": data["stock"],
            "image_url": data["image_url"],
        }
        collection.upsert(
            documents=[document],
            metadatas=[metadata],
            ids=[f"prod_{product.id}"],
        )
        logger.info("ChromaDB real-time upsert successful for product %s (%s)", product.id, product.name)
        return True
    except Exception as exc:
        logger.warning("Error in real-time ChromaDB upsert for product %s: %s", getattr(product, "id", "?"), exc)
        return False


def delete_single_product(product_id: int) -> bool:
    """Delete a single product vector from ChromaDB collection in real time."""
    try:
        collection = get_chroma_collection()
        if collection is None:
            return False
        collection.delete(ids=[f"prod_{product_id}"])
        logger.info("ChromaDB real-time delete successful for product %s", product_id)
        return True
    except Exception as exc:
        logger.warning("Error in real-time ChromaDB delete for product %s: %s", product_id, exc)
        return False


# ============================================================
# DYNAMIC CATEGORY & BRAND DATABASE LOADERS
# ============================================================

def get_store_categories() -> List[str]:
    """Fetch active store categories dynamically from the database."""
    try:
        categories = list(
            Category.objects.filter(is_active=True)
            .order_by("name")
            .values_list("name", flat=True)
        )
        if categories:
            return categories
    except Exception as exc:
        logger.debug("Database error fetching categories: %s", exc)
    return []


def get_store_brands() -> List[str]:
    """Fetch all brands dynamically from the database."""
    try:
        brands = list(
            Brand.objects.all()
            .order_by("name")
            .values_list("name", flat=True)
        )
        if brands:
            return brands
    except Exception as exc:
        logger.debug("Database error fetching brands: %s", exc)
    return []


def get_allowed_brands_for_category(category: Optional[str]) -> List[str]:
    """
    Return brands associated with the given category dynamically from the database
    via Brand.categories ManyToMany relation and active Product linkages.
    """
    if not category:
        return []

    try:
        # 1. Brands associated via Brand.categories M2M relation
        brands_from_rel = list(
            Brand.objects.filter(categories__name__iexact=category)
            .values_list("name", flat=True)
        )
        # 2. Brands associated via active products in this category
        brands_from_products = list(
            Product.objects.filter(
                is_active=True,
                category__name__iexact=category,
                brand__isnull=False,
            )
            .values_list("brand__name", flat=True)
            .distinct()
        )
        combined = sorted(list(set(brands_from_rel + brands_from_products)))
        if combined:
            return combined
    except Exception as exc:
        logger.debug("Database error getting allowed brands for category %s: %s", category, exc)

    return []


# Common customer terms mapped to the canonical store category names.
CATEGORY_ALIASES = {
    # Smartphones
    "iphone": "Smartphones",
    "iphones": "Smartphones",
    "galaxy": "Smartphones",
    "pixel": "Smartphones",
    "phone": "Smartphones",
    "phones": "Smartphones",
    "mobile": "Smartphones",
    "mobiles": "Smartphones",
    "smartphone": "Smartphones",
    "smartphones": "Smartphones",
    "handset": "Smartphones",
    "handsets": "Smartphones",
    "cellphone": "Smartphones",
    "cellphones": "Smartphones",
    "cell phone": "Smartphones",
    "cell phones": "Smartphones",
    "mobile phone": "Smartphones",
    "mobile phones": "Smartphones",

    # Laptops
    "macbook": "Laptops",
    "macbooks": "Laptops",
    "laptop": "Laptops",
    "laptops": "Laptops",
    "notebook": "Laptops",
    "notebooks": "Laptops",
    "ultrabook": "Laptops",
    "ultrabooks": "Laptops",
    "thinkpad": "Laptops",
    "zenbook": "Laptops",
    "pavilion": "Laptops",
    "vivobook": "Laptops",
    "legion": "Laptops",
    "rog": "Laptops",

    # Tablets
    "ipad": "Tablets",
    "ipads": "Tablets",
    "tablet": "Tablets",
    "tablets": "Tablets",
    "tab": "Tablets",
    "tabs": "Tablets",

    # Smartwatches
    "smartwatch": "Smartwatches",
    "smartwatches": "Smartwatches",
    "watch": "Smartwatches",
    "watches": "Smartwatches",
    "apple watch": "Smartwatches",
    "iwatch": "Smartwatches",
    "galaxy watch": "Smartwatches",
    "fitness band": "Smartwatches",
    "smart band": "Smartwatches",

    # Headphones & Audio
    "earbuds": "Headphones & Earphones",
    "airpods": "Headphones & Earphones",
    "headphones": "Headphones & Earphones",
    "headphone": "Headphones & Earphones",
    "earphones": "Headphones & Earphones",
    "earphone": "Headphones & Earphones",
    "headset": "Headphones & Earphones",
    "headsets": "Headphones & Earphones",
    "tws": "Headphones & Earphones",
    "in-ear": "Headphones & Earphones",
    "on-ear": "Headphones & Earphones",
    "over-ear": "Headphones & Earphones",

    # Speakers
    "speaker": "Speakers",
    "speakers": "Speakers",
    "soundbar": "Speakers",
    "soundbars": "Speakers",
    "bluetooth speaker": "Speakers",
    "subwoofer": "Speakers",

    # Cameras
    "camera": "Cameras & Photography",
    "cameras": "Cameras & Photography",
    "dslr": "Cameras & Photography",
    "mirrorless": "Cameras & Photography",
    "gopro": "Cameras & Photography",
    "action cam": "Cameras & Photography",

    # Desktop & Monitors
    "desktop": "Desktop Computers",
    "desktops": "Desktop Computers",
    "pc": "Desktop Computers",
    "pcs": "Desktop Computers",
    "computer": "Desktop Computers",
    "computers": "Desktop Computers",
    "all-in-one": "Desktop Computers",
    "workstation": "Desktop Computers",
    "monitor": "Monitors & Displays",
    "monitors": "Monitors & Displays",
    "display": "Monitors & Displays",
    "displays": "Monitors & Displays",
    "screen": "Monitors & Displays",
    "screens": "Monitors & Displays",

    # Gaming Consoles
    "gaming console": "Gaming Consoles",
    "gaming consoles": "Gaming Consoles",
    "playstation": "Gaming Consoles",
    "ps5": "Gaming Consoles",
    "ps4": "Gaming Consoles",
    "xbox": "Gaming Consoles",
    "nintendo": "Gaming Consoles",
    "switch": "Gaming Consoles",
    "steam deck": "Gaming Consoles",

    # Keyboards & Mice
    "keyboard": "Keyboards",
    "keyboards": "Keyboards",
    "mechanical keyboard": "Keyboards",
    "mouse": "Mice",
    "mice": "Mice",
    "trackpad": "Mice",

    # Storage & Components
    "ssd": "Storage Devices",
    "hdd": "Storage Devices",
    "hard disk": "Storage Devices",
    "hard drive": "Storage Devices",
    "pendrive": "Storage Devices",
    "pen drive": "Storage Devices",
    "flash drive": "Storage Devices",
    "memory card": "Storage Devices",
    "sd card": "Storage Devices",
    "graphic card": "PC Components",
    "graphics card": "PC Components",
    "gpu": "PC Components",
    "processor": "PC Components",
    "motherboard": "PC Components",
    "ram": "PC Components",

    # Chargers & Cables & Networking & Others
    "charger": "Chargers & Power Banks",
    "chargers": "Chargers & Power Banks",
    "powerbank": "Chargers & Power Banks",
    "powerbanks": "Chargers & Power Banks",
    "power bank": "Chargers & Power Banks",
    "power banks": "Chargers & Power Banks",
    "cable": "Cables & Adapters",
    "cables": "Cables & Adapters",
    "hdmi": "Cables & Adapters",
    "adapter": "Cables & Adapters",
    "adapters": "Cables & Adapters",
    "router": "Networking Devices",
    "routers": "Networking Devices",
    "wifi": "Networking Devices",
    "printer": "Printers & Scanners",
    "printers": "Printers & Scanners",
    "scanner": "Printers & Scanners",
    "scanners": "Printers & Scanners",
    "smart home": "Smart Home Devices",
}

# Product-family aliases identify the correct brand even when the customer
# does not type the brand name explicitly.
BRAND_ALIASES = {
    "iphone": "Apple",
    "ipad": "Apple",
    "macbook": "Apple",
    "airpods": "Apple",
    "playstation": "Sony",
    "xbox": "Microsoft",
}


def _word_pattern(value: str) -> str:
    """Create a safe word-boundary regex for a user-entered term."""
    return r"\b" + re.escape(normalize_text(value)) + r"\b"


def detect_category(query: str) -> Optional[str]:
    """Detect category dynamically from database Category records and aliases."""
    normalized = normalize_text(query)
    db_categories = get_store_categories()

    # 1. Exact or stemmed match against dynamic database categories (longest first)
    for category in sorted(db_categories, key=len, reverse=True):
        cat_norm = normalize_text(category)
        if re.search(_word_pattern(cat_norm), normalized):
            return category
        # Singular form for simple plural categories (e.g. Laptops -> laptop, Smartphones -> smartphone)
        if cat_norm.endswith("s") and len(cat_norm) > 3:
            singular = cat_norm[:-1]
            if re.search(_word_pattern(singular), normalized):
                return category

    # 2. Customer-friendly aliases matching database categories
    for alias, cat_target in sorted(CATEGORY_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(_word_pattern(alias), normalized):
            matched_db = next((c for c in db_categories if c.lower() == cat_target.lower()), None)
            if matched_db:
                return matched_db
            if not db_categories:
                return cat_target

    return None


def detect_brands(query: str, category: Optional[str] = None) -> List[str]:
    """Detect brands dynamically from the database, optionally restricted to a category."""
    normalized = normalize_text(query)
    words = set(re.findall(r"[a-z0-9]+", normalized))

    if category:
        allowed_brands = get_allowed_brands_for_category(category)
    else:
        allowed_brands = get_store_brands()

    matched = []

    # Check aliases first (e.g. iphone -> Apple)
    for alias, brand_name in BRAND_ALIASES.items():
        if alias in words:
            if not allowed_brands or any(b.lower() == brand_name.lower() for b in allowed_brands):
                matched.append(brand_name)

    # Exact whole-word / multi-word matching against database brands
    for brand in sorted(allowed_brands, key=len, reverse=True):
        brand_words = set(re.findall(r"[a-z0-9]+", normalize_text(brand)))
        if brand_words and brand_words.issubset(words):
            matched.append(brand)

    return list(dict.fromkeys(matched))


# ============================================================
# TYPO & PHONETIC CORRECTION DICTIONARY
# ============================================================

TYPO_CORRECTIONS = {
    "laptap": "laptop",
    "laptaps": "laptops",
    "loptop": "laptop",
    "loptops": "laptops",
    "leptop": "laptop",
    "leptops": "laptops",
    "samsang": "samsung",
    "sumsung": "samsung",
    "samson": "samsung",
    "makbook": "macbook",
    "macbok": "macbook",
    "mcbook": "macbook",
    "mac book": "macbook",
    "ipade": "ipad",
    "ipades": "ipads",
    "keboard": "keyboard",
    "keybord": "keyboard",
    "mose": "mouse",
    "mouses": "mice",
    "earfone": "earphone",
    "earfones": "earphones",
    "headfone": "headphone",
    "headfones": "headphones",
    "phon": "phone",
    "fone": "phone",
    "fones": "phones",
    "smartfone": "smartphone",
    "smartfones": "smartphones",
    "logiteck": "logitech",
    "zenbok": "zenbook",
    "moniter": "monitor",
    "moniters": "monitors",
    "speeker": "speaker",
    "speekers": "speakers",
    "charcher": "charger",
    "chargr": "charger",
    "cabel": "cable",
    "cabels": "cables",
}


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def normalize_text(text: str) -> str:
    """
    Normalize user input for more reliable matching.
    Converts 60k -> 60000, 30k -> 30000, 1.5l -> 150000, 20 hazaar -> 20000, etc.
    Corrects common phonetic typos and Hinglish terms.
    """
    text = text.lower().strip()

    # Apply typo corrections for whole words
    for typo, correction in TYPO_CORRECTIONS.items():
        text = re.sub(r"\b" + re.escape(typo) + r"\b", correction, text)

    # Remove commas from prices: ₹60,000 -> ₹60000
    text = text.replace(",", "")

    # Expand shorthand numbers: 60k -> 60000, 1.5k -> 1500, 70 k -> 70000
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*k\b",
        lambda m: str(int(float(m.group(1)) * 1000)),
        text,
    )
    # Expand lakhs: 1.5l -> 150000, 1lakh -> 100000, 2 lac -> 200000, 1.5 lacs -> 150000
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:lakhs?|lacs?|l\b)",
        lambda m: str(int(float(m.group(1)) * 100000)),
        text,
    )
    # Expand thousands/hazaar: 20 hazaar -> 20000, 50 hazar -> 50000, 20 hajar -> 20000
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:hazaar|hazar|hazars|hajars?)\b",
        lambda m: str(int(float(m.group(1)) * 1000)),
        text,
    )
    # Expand crores: 1 crore -> 10000000, 1.2 cr -> 12000000
    text = re.sub(
        r"(\d+(?:\.\d+)?)\s*(?:crores?|cr\b)",
        lambda m: str(int(float(m.group(1)) * 10000000)),
        text,
    )
    # Normalize Hinglish price phrasing: "60k k andr" -> "under 60000", "50000 ke andar" -> "under 50000"
    text = re.sub(
        r"(\d+)\s*(?:k\s*)?(?:k\s*andr|ke\s*andar|k\s*andar|k\s*bheetar|ke\s*bheetar|me|mein)\b",
        r"under \1",
        text,
    )
    # Value-for-money slang normalization
    text = re.sub(r"\bcheap\s+and\s+best\b", "best value budget", text)
    text = re.sub(r"\bsasta\s+(?:and|aur)\s+tikau\b", "best affordable", text)

    return text


# ============================================================
# PRICE FILTER EXTRACTION
# ============================================================

def extract_price_filter(query: str) -> Dict[str, Optional[float]]:
    """
    Extract min/max budget constraints from natural language query.
    Handles:
      "under 60000"       -> max: 60000
      "below 30k"         -> max: 30000
      "above 50000"       -> min: 50000
      "between 30k and 60k" -> min: 30000, max: 60000
      "around 40000"      -> min: 28000, max: 52000 (+/- 30%)
      "60000 budget"      -> min: 42000, max: 78000 (+/- 30%)
    """
    query = normalize_text(query)

    result: Dict[str, Optional[float]] = {
        "min_price": None,
        "max_price": None,
    }

    # Range: between 30000 and 60000 / 30000 to 60000 / 30000-60000
    range_match = re.search(
        r"(?:between\s+)?₹?(\d+(?:\.\d+)?)\s*(?:to|-|and)\s*₹?(\d+(?:\.\d+)?)",
        query,
    )
    if range_match:
        p1 = float(range_match.group(1))
        p2 = float(range_match.group(2))
        result["min_price"] = min(p1, p2)
        result["max_price"] = max(p1, p2)
        return result

    # Around / approx / budget / nearby
    around_match = re.search(
        r"(?:around|approx(?:imately)?|about|nearby|budget\s*(?:of|is|:)?)\s*₹?(\d+(?:\.\d+)?)",
        query,
    )
    if around_match:
        target = float(around_match.group(1))
        result["min_price"] = target * 0.70
        result["max_price"] = target * 1.30
        return result

    # "60000 budget" / "50k budget"
    budget_after = re.search(
        r"₹?(\d+(?:\.\d+)?)\s*(?:budget|range|price point)",
        query,
    )
    if budget_after:
        target = float(budget_after.group(1))
        result["min_price"] = target * 0.70
        result["max_price"] = target * 1.30
        return result

    # Bare number when words like "budget", "for", "in" precede it
    bare_budget = re.search(
        r"(?:for|in|within)\s+₹?(\d+(?:\.\d+)?)\s*(?:rs|rupees|inr)?(?:\s|$)",
        query,
    )
    if bare_budget:
        target = float(bare_budget.group(1))
        if target >= 1000:
            result["min_price"] = target * 0.70
            result["max_price"] = target * 1.30
            return result

    # Max: under 60000, below ₹60000, less than 60000, upto 60000
    max_match = re.search(
        r"(?:under|below|less than|upto|up to|max(?:imum)?)[^\d₹]*₹?(\d+(?:\.\d+)?)",
        query,
    )
    if max_match:
        result["max_price"] = float(max_match.group(1))
        return result

    # Min: above 50000, over 50000, more than 50000, min 40000
    min_match = re.search(
        r"(?:above|over|more than|greater than|min(?:imum)?)[^\d₹]*₹?(\d+(?:\.\d+)?)",
        query,
    )
    if min_match:
        result["min_price"] = float(min_match.group(1))
        return result

    return result


# ============================================================
# ATTRIBUTE KEYWORDS
# ============================================================

STOP_WORDS = {
    "the", "a", "an", "for", "with", "and", "or", "to", "from",
    "show", "give", "me", "some", "best", "good", "want", "need",
    "looking", "find", "product", "products", "item", "items",
    "please", "available", "available?", "under", "below", "above",
    "over", "less", "more", "than", "price", "cheap", "budget",
    "around", "about", "approx", "which", "what", "has", "have", "can",
}


def extract_search_keywords(query: str) -> List[str]:
    query = normalize_text(query)

    # Remove price expressions
    query = re.sub(
        r"(?:under|below|less than|upto|up to|above|over|more than|around|between|to)"
        r"[^\d₹]*₹?\d+",
        " ",
        query,
    )

    words = re.findall(r"[a-z0-9]+", query)
    keywords = []

    for word in words:
        if len(word) <= 1:
            continue
        if word in STOP_WORDS:
            continue
        keywords.append(word)

    return list(dict.fromkeys(keywords))


# ============================================================
# DATABASE SEARCH
# ============================================================

def database_product_search(
    query: str,
    n_results: int = 6,
) -> List[Dict[str, Any]]:

    normalized_query = normalize_text(query)

    matched_category = detect_category(normalized_query)
    matched_brands = detect_brands(normalized_query, category=matched_category)
    price_filter = extract_price_filter(normalized_query)
    keywords = extract_search_keywords(normalized_query)

    qs = (
        Product.objects
        .filter(is_active=True)
        .select_related("category", "brand")
    )

    # CATEGORY FILTER — strictly use the detected master category.
    if matched_category:
        qs = qs.filter(category__name__iexact=matched_category)

    # BRAND FILTER
    if matched_brands:
        brand_query = Q()
        for brand in matched_brands:
            brand_query |= Q(brand__name__iexact=brand)
        qs = qs.filter(brand_query)

    # PRICE FILTER
    if price_filter["min_price"] is not None:
        qs = qs.filter(price__gte=price_filter["min_price"])

    if price_filter["max_price"] is not None:
        qs = qs.filter(price__lte=price_filter["max_price"])

    # SORTING / ORDERING INTENT (e.g. cheapest mouse, highest discount, premium/flagship)
    if re.search(r"\b(?:cheapest|lowest\s+price|most\s+affordable|sasta|cheap)\b", normalized_query):
        qs = qs.order_by("price")
    elif re.search(r"\b(?:most\s+expensive|highest\s+price|costliest|premium|flagship|top\s+end)\b", normalized_query):
        qs = qs.order_by("-price")
    elif re.search(r"\b(?:best\s+discount|highest\s+discount|best\s+deal|top\s+offer)\b", normalized_query):
        qs = qs.order_by("-discount", "price")

    # KEYWORD SEARCH (matching name, description, specs, brand, category)
    if keywords:
        brand_cat_words = set(matched_brands)
        if matched_category:
            brand_cat_words.add(matched_category.lower())
        
        filtered_keywords = [
            k for k in keywords 
            if k.lower() not in [b.lower() for b in brand_cat_words]
            and k not in [
                "laptop", "laptops", "laptos", "phone", "phones", "mobile", "mobiles",
                "smartphone", "smartphones", "cellphone", "cellphones", "handset", "handsets",
                "keyboard", "keyboards", "computer", "computers"
            ]
        ]

        if filtered_keywords:
            keyword_query = Q()
            for keyword in filtered_keywords:
                alt_keyword = re.sub(r"(\d+)(gb|tb)", r"\1 \2", keyword) if re.search(r"\d+(?:gb|tb)", keyword) else None
                sub_q = (
                    Q(name__icontains=keyword)
                    | Q(description__icontains=keyword)
                    | Q(specifications__icontains=keyword)
                )
                if alt_keyword:
                    sub_q |= (
                        Q(name__icontains=alt_keyword)
                        | Q(description__icontains=alt_keyword)
                        | Q(specifications__icontains=alt_keyword)
                    )
                keyword_query |= sub_q

            keyword_results = qs.filter(keyword_query)
            if keyword_results.exists():
                qs = keyword_results

    # If the exact filters return nothing, broaden ONLY inside the detected
    # category. Never cross into another category.
    if not qs.exists() and matched_category:
        fallback_cat_qs = Product.objects.filter(
            is_active=True,
            category__name__iexact=matched_category,
        )

        if price_filter["max_price"] is not None:
            price_qs = fallback_cat_qs.filter(
                price__lte=price_filter["max_price"] * 1.5
            )
            qs = price_qs if price_qs.exists() else fallback_cat_qs
        else:
            qs = fallback_cat_qs

    results = []
    seen_ids = set()
    for product in qs[:n_results]:
        results.append(product_to_dict(product))
        seen_ids.add(product.id)

    # Backfill strictly from the same category.
    # If a matched_category was detected OR if initial results share a category,
    # NEVER allow backfill from unrelated categories.
    target_category = matched_category
    if not target_category and results and results[0].get("category"):
        target_category = results[0]["category"]

    if target_category and len(results) < n_results:
        remaining = n_results - len(results)
        backfill_qs = (
            Product.objects
            .filter(is_active=True, category__name__iexact=target_category)
            .exclude(id__in=seen_ids)
            .select_related("category", "brand")
        )

        if matched_brands:
            brand_q = Q()
            for b in matched_brands:
                brand_q |= Q(brand__name__iexact=b)
            brand_backfill = backfill_qs.filter(brand_q)
            if brand_backfill.exists():
                backfill_qs = brand_backfill

        for product in backfill_qs[:remaining]:
            results.append(product_to_dict(product))
            seen_ids.add(product.id)

    return results


# ============================================================
# SEMANTIC SEARCH
# ============================================================

def semantic_product_search(
    query: str,
    n_results: int = 6,
    matched_category: Optional[str] = None,
) -> List[Dict[str, Any]]:

    collection = get_chroma_collection()
    if not collection:
        return []

    try:
        count = collection.count()
        if count == 0:
            return []

        query_filter = None
        if matched_category:
            query_filter = {"category": {"$eq": matched_category}}

        kwargs: Dict[str, Any] = {
            "query_texts": [query],
            "n_results": min(n_results * 2, count),
        }
        if query_filter:
            try:
                kwargs["where"] = query_filter
            except Exception:
                pass

        result = collection.query(**kwargs)

        metadatas = result.get("metadatas", [])
        if not metadatas or not metadatas[0]:
            return []

        items = metadatas[0]
        if matched_category:
            # Filter in Python to guarantee category integrity
            filtered = [
                m for m in items
                if str(m.get("category", "")).strip().lower() == matched_category.strip().lower()
            ]
            if filtered:
                items = filtered

        # Live Database Hydration: Retrieve fresh real-time attributes from PostgreSQL
        product_ids = []
        for item in items:
            pid = item.get("product_id")
            if pid:
                try:
                    product_ids.append(int(pid))
                except (ValueError, TypeError):
                    pass

        if product_ids:
            live_products = (
                Product.objects
                .filter(id__in=product_ids, is_active=True)
                .select_related("category", "brand")
            )
            live_map = {p.id: product_to_dict(p) for p in live_products}

            # Preserve semantic ranking order and only include active items
            hydrated_results = []
            for pid in product_ids:
                if pid in live_map:
                    hydrated_results.append(live_map[pid])
            if hydrated_results:
                return hydrated_results[:n_results]

        return items[:n_results]

    except Exception as exc:
        logger.warning("Semantic search failed: %s", exc)
        return []


# ============================================================
# MAIN RETRIEVAL
# ============================================================

def retrieve_relevant_products(
    query: str,
    n_results: int = 6,
) -> List[Dict[str, Any]]:

    if not query or not query.strip():
        return []

    matched_category = detect_category(query)

    # 1. Exact / structured DB search with price & brand & category parsing
    db_results = database_product_search(query, n_results)
    if db_results:
        if matched_category:
            db_results = [r for r in db_results if str(r.get("category", "")).strip().lower() == matched_category.strip().lower()]
        if db_results:
            return db_results

    # 2. Semantic search with category constraint
    semantic_results = semantic_product_search(query, n_results, matched_category=matched_category)
    if semantic_results:
        if matched_category:
            semantic_results = [r for r in semantic_results if str(r.get("category", "")).strip().lower() == matched_category.strip().lower()]
        if semantic_results:
            return semantic_results

    # 3. Fallback search (strictly respect category if detected)
    keywords = extract_search_keywords(query)
    if not keywords:
        if matched_category:
            cat_products = Product.objects.filter(
                is_active=True
            ).filter(
                Q(category__name__iexact=matched_category)
                | Q(category__name__icontains=matched_category.rstrip('s'))
            ).select_related("category", "brand")[:n_results]
            return [product_to_dict(p) for p in cat_products]
        return []

    fallback_query = Q()
    for keyword in keywords[:4]:
        fallback_query |= (
            Q(name__icontains=keyword)
            | Q(description__icontains=keyword)
            | Q(brand__name__icontains=keyword)
        )

    qs = Product.objects.filter(is_active=True).filter(fallback_query)
    if matched_category:
        qs = qs.filter(
            Q(category__name__iexact=matched_category)
            | Q(category__name__icontains=matched_category.rstrip('s'))
        )

    products = qs.select_related("category", "brand")[:n_results]

    return [product_to_dict(product) for product in products]


# ============================================================
# ORDER TRACKING INTENT DETECTION & FORMATTING
# ============================================================

def format_order_tracking_details(order: Any, title_prefix: str = "") -> str:
    """
    Format an order with visual progress stepper, item breakdown,
    destination address, courier transit estimates, and contextual actions.
    """
    status = order.status

    # Visual Order Progress Stepper
    steppers = {
        "Pending": "⏳ Order Placed ── ⚪ Processing ── ⚪ In Transit ── ⚪ Delivered",
        "Payment_Pending": "⏳ Order Placed ── 💳 Processing Payment ── ⚪ In Transit ── ⚪ Delivered",
        "Paid": "✅ Order Placed ── 💳 Payment Confirmed ── 🚚 Preparing Dispatch ── ⚪ Delivered",
        "Shipped": "✅ Order Placed ── ✅ Payment Confirmed ── 🚚 In Transit ── ⚪ Out for Delivery",
        "Delivered": "✅ Order Placed ── ✅ Payment Confirmed ── ✅ In Transit ── 📦 Delivered",
        "Cancelled": "❌ Order Cancelled",
    }
    stepper = steppers.get(status, f"📋 Status: {status}")

    status_emojis = {
        "Pending": "⏳",
        "Payment_Pending": "💳",
        "Paid": "✅",
        "Shipped": "🚚",
        "Delivered": "📦",
        "Cancelled": "❌",
    }
    emoji = status_emojis.get(status, "📋")

    items_list = []
    for item in order.items.all():
        pname = item.product.name if item.product else "Item"
        items_list.append(f"• {item.quantity}x {pname} (₹{item.price_at_purchase:,.2f})")
    items_text = "\n".join(items_list) if items_list else "No items recorded."

    address_snippet = ""
    if order.recipient_name or order.city:
        address_snippet = f"\n• **Shipping Destination:** {order.recipient_name or ''}, {order.city or ''}, {order.state or ''} {order.postal_code or ''}".strip()

    date_str = order.created_at.strftime("%d %B %Y at %I:%M %p")

    # Delivery transit estimates & contextual tips
    carrier_str = f"• **Logistics Carrier:** {order.carrier_name} (Tracking: `{order.tracking_number}`)\n" if getattr(order, 'tracking_number', None) else ""
    delivery_timeline_str = f"• **Delivery Estimate:** {order.delivery_status_display}\n" if hasattr(order, 'delivery_status_display') else ""

    if status == "Shipped":
        transit_info = f"{carrier_str}{delivery_timeline_str}" if (carrier_str or delivery_timeline_str) else "• **Estimated Delivery:** 2–4 business days via Express Courier partner.\n"
        tip = "💡 *Your package is on its way! Track live carrier updates or download your invoice under [My Orders](/orders/my-orders/).*"
    elif status in ("Paid", "Pending", "Payment_Pending"):
        transit_info = f"{delivery_timeline_str}" if delivery_timeline_str else "• **Estimated Delivery:** 3–5 business days after dispatch.\n"
        tip = "💡 *Tip: You can cancel or modify this order before it is dispatched from your [My Orders](/orders/my-orders/) dashboard.*"
    elif status == "Delivered":
        delivery_msg = f"• **Delivery Status:** {order.delivery_status_display}\n" if hasattr(order, 'delivery_status_display') else "• **Delivery Status:** Successfully delivered.\n"
        transit_info = f"{delivery_msg}{carrier_str}"
        tip = "💡 *Need help with your product? EasyTech offers a 7-day hassle-free replacement and return policy on eligible electronics.*"
    elif status == "Cancelled":
        transit_info = "• **Order Cancelled:** No active transit.\n"
        tip = "💡 *This order was cancelled. If you need assistance or wish to re-order, explore our latest deals!*"
    else:
        transit_info = f"{delivery_timeline_str}\n" if delivery_timeline_str else ""
        tip = "💡 *Visit your [My Orders](/orders/my-orders/) dashboard for full order management.*"

    if title_prefix:
        header_title = f"{title_prefix}Order Status for #{order.id}"
    else:
        header_title = f"Order Status for #{order.id}"

    reply = (
        f"📦 **{header_title}**\n\n"
        f"• **Order #{order.id} Progress:**\n`{stepper}`\n\n"
        f"• **Live Status:** {emoji} **{order.get_status_display() if hasattr(order, 'get_status_display') else order.status}**\n"
        f"• **Order Placed:** {date_str}\n"
        f"• **Total Amount:** ₹{order.total_amount:,.2f}\n"
        f"{transit_info}"
        f"{address_snippet}\n\n"
        f"**Items in this Order:**\n{items_text}\n\n"
        f"{tip}\n\n"
        f"You can view complete order details, download the invoice, or manage your order on your [My Orders](/orders/my-orders/) dashboard."
    )
    return reply


def check_order_tracking_intent(
    message: str,
    user: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Detects if the user is asking to track an order (e.g. 'where is my order #5',
    'track order 12', 'track my latest order', 'order status', 'my orders').
    Supports secure guest tracking via email verification and logged-in instant tracking.
    Returns structured response if intent detected, else None.
    """
    if not message:
        return None

    # Regex patterns for order ID (e.g. "order #1", "track 5", "order no 12", "order 3")
    order_id_match = re.search(
        r"(?:order|track|status|item|package|shipment|delivery)\s*(?:#|no\.?|number|id|num)?\s*(\d+)",
        message,
        re.IGNORECASE,
    )
    if not order_id_match:
        order_id_match = re.search(r"#(\d+)", message)

    # Regex patterns for general order tracking inquiries
    general_order_intent = re.search(
        r"(?:\bwhere\s+(?:is\s+)?(?:my\s+|the\s+)?(?:latest\s+|last\s+|recent\s+)?order\b"
        r"|\btrack\w*\s+(?:my\s+|an?\s+|the\s+)?(?:latest\s+|last\s+|recent\s+)?order\b"
        r"|\bmy\s+(?:latest\s+|last\s+|recent\s+)?orders?\b"
        r"|\border\s*track\w*\b|\border\s*t[ar]+ck\w*\b|\border\s*details?\b|\border\s*status\b"
        r"|\bcheck\s+(?:my\s+|the\s+)?(?:latest\s+|last\s+|recent\s+)?order\b"
        r"|\bstatus\s+of\s+(?:my\s+|the\s+)?(?:latest\s+|last\s+|recent\s+)?order\b"
        r"|\btrack\s+(?:package|parcel|shipment|delivery)\b"
        r"|\bwhere\s+is\s+my\s+(?:package|parcel|shipment|delivery)\b"
        r"|\b(?:did\s+my\s+order\s+ship|when\s+will\s+my\s+order\s+arrive|has\s+my\s+order\s+shipped)\b)",
        message,
        re.IGNORECASE,
    )

    if not order_id_match and not general_order_intent:
        return None

    from orders.models import Order

    # Check for email in message for guest verification
    email_match = re.search(
        r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
        message,
    )
    guest_email = email_match.group(0).strip().lower() if email_match else None

    # Handle unauthenticated guest
    if not user or not getattr(user, "is_authenticated", False):
        if order_id_match and guest_email:
            # Secure guest verification: check order ID matches guest email
            try:
                order_id = int(order_id_match.group(1))
                order = (
                    Order.objects
                    .filter(id=order_id)
                    .prefetch_related("items__product")
                    .select_related("user")
                    .first()
                )
                if order and order.user and order.user.email.strip().lower() == guest_email:
                    return {
                        "reply": format_order_tracking_details(order, title_prefix="Verified Guest Tracking: "),
                        "products": [],
                        "model": "order-tracking",
                    }
                else:
                    return {
                        "reply": (
                            f"⚠️ **Order Verification Failed**\n\n"
                            f"We could not verify **Order #{order_id}** with the email address `{guest_email}`. "
                            "Please check that both the Order ID and email address match your checkout confirmation, "
                            "or please log in to your account to view all orders."
                        ),
                        "products": [],
                        "model": "order-tracking",
                    }
            except Exception as exc:
                logger.exception("Error verifying guest order: %s", exc)

        elif order_id_match:
            order_id = order_id_match.group(1)
            return {
                "reply": (
                    f"📦 **Guest Order Tracking**\n\n"
                    f"To view live tracking details for **Order #{order_id}**, please verify your registered email address:\n\n"
                    f"👉 *\"Track order #{order_id} email: yourname@example.com\"*\n\n"
                    "Or please log in to your account to track all your orders directly."
                ),
                "products": [],
                "model": "order-tracking",
            }

        return {
            "reply": (
                "📦 **Order Tracking Service**\n\n"
                "To track your orders and view live shipping updates, please log in to your EasyTech account.\n\n"
                "If you placed an order as a guest, you can track it anytime by providing your order number and email:\n"
                "👉 *\"Track order #123 email: yourname@example.com\"*"
            ),
            "products": [],
            "model": "order-tracking",
        }

    # Case 1: Specific Order ID requested by authenticated user
    if order_id_match:
        try:
            order_id = int(order_id_match.group(1))
            order = Order.objects.filter(user=user, id=order_id).prefetch_related("items__product").first()
            if not order:
                exists_other = Order.objects.filter(id=order_id).exists()
                if exists_other:
                    return {
                        "reply": (
                            f"⚠️ **Order #{order_id} Not Found**\n\n"
                            f"Order #{order_id} is not associated with your current account ({getattr(user, 'email', '')}). "
                            "Please make sure you are logged into the account used when placing the order."
                        ),
                        "products": [],
                        "model": "order-tracking",
                    }
                return {
                    "reply": (
                        f"⚠️ **Order #{order_id} Not Found**\n\n"
                        f"We couldn't find an order with ID #{order_id} in your EasyTech account. "
                        "Please check your order number in your confirmation email or visit your [My Orders](/orders/my-orders/) page."
                    ),
                    "products": [],
                    "model": "order-tracking",
                }

            return {
                "reply": format_order_tracking_details(order),
                "products": [],
                "model": "order-tracking",
            }
        except Exception as exc:
            logger.exception("Error checking order status: %s", exc)

    # Case 2: Latest Order / General Order Tracking for authenticated user
    user_orders = Order.objects.filter(user=user).order_by("-created_at").prefetch_related("items__product")
    if not user_orders.exists():
        return {
            "reply": (
                "📦 **Your Orders**\n\n"
                "You haven't placed any orders with EasyTech yet! "
                "Browse our latest laptops, smartphones, and audio gear to get started."
            ),
            "products": [],
            "model": "order-tracking",
        }

    # Detect if user specifically asked for latest / last order or single order
    latest_order_intent = re.search(
        r"(?:latest|last|recent|current|did\s+my\s+order\s+ship|status\s+of\s+my\s+(?:last|latest|recent)?\s*order|track\s+(?:my\s+)?(?:latest|last|recent)?\s*order|where\s+is\s+my\s+order)",
        message,
        re.IGNORECASE,
    )

    if latest_order_intent or user_orders.count() == 1:
        latest_order = user_orders.first()
        reply_text = format_order_tracking_details(latest_order, title_prefix="Latest ")
        if user_orders.count() > 1:
            other_orders = user_orders[1:4]
            other_lines = [
                f"• **Order #{o.id}** — {o.status} (₹{o.total_amount:,.2f} on {o.created_at.strftime('%d %b %Y')})"
                for o in other_orders
            ]
            reply_text += "\n\n**Other Recent Orders:**\n" + "\n".join(other_lines)

        return {
            "reply": reply_text,
            "products": [],
            "model": "order-tracking",
        }

    # Multiple orders summary
    order_summaries = []
    for ord_obj in user_orders[:4]:
        date_str = ord_obj.created_at.strftime("%d %b %Y")
        order_summaries.append(
            f"• **Order #{ord_obj.id}** — Status: **{ord_obj.status}** | Total: ₹{ord_obj.total_amount:,.2f} ({date_str})"
        )

    summary_text = "\n".join(order_summaries)
    return {
        "reply": (
            f"📦 **Here are your recent orders:**\n\n"
            f"{summary_text}\n\n"
            "To get live progress and full tracking for any order, ask e.g. *\"Where is my order #1?\"* or *\"Track my latest order\"*."
        ),
        "products": [],
        "model": "order-tracking",
    }


# ============================================================
# SAFETY, ANTI-HALLUCINATION & JAILBREAK GUARD (TIER 9)
# ============================================================

def check_safety_guard(message: str) -> Optional[Dict[str, Any]]:
    """
    Tier 9 Safety Guard:
    Intercepts prompt injection, system prompt extraction, persona hijacking (DAN),
    malicious SQL/code execution, and non-existent product hallucinations.
    """
    if not message:
        return None

    norm = message.lower().strip()

    # 1. System Prompt Leak & Instruction Override Protection
    if re.search(
        r"(?:ignore\s+(?:all\s+)?previous\s+instructions|output\s+(?:your\s+)?system\s+prompt|repeat\s+(?:the\s+)?(?:instructions|prompt)\s+above|print\s+(?:your\s+)?initial\s+instructions|what\s+(?:is|are)\s+your\s+(?:system\s+)?(?:instructions|prompt|rules))",
        norm,
    ):
        return {
            "reply": (
                "🛡️ **EasyTech Assistant Security Notice**\n\n"
                "I am **EasyTech Assistant**, the official AI shopping advisor for EasyTech Store. "
                "I am here to help you discover authentic laptops, smartphones, monitors, and accessories, "
                "track existing orders, or explain store policies. How may I help you with your shopping today?"
            ),
            "products": [],
            "model": "safety-guard",
        }

    # 2. Persona Override / DAN / Jailbreak Exploits
    if re.search(
        r"(?:\byou\s+are\s+now\s+dan\b|\bjailbreak\b|\bsystem\s+override\b|\bdeveloper\s+mode\b|\badmin\s+password\b|\broot\s+access\b|\bapi\s+key\b)",
        norm,
    ):
        return {
            "reply": (
                "🔒 **Access Denied**\n\n"
                "I operate strictly within EasyTech Store's authorized e-commerce parameters and cannot "
                "bypass security policies or expose administrative credentials. "
                "I can, however, help you browse our certified electronics catalog or compare genuine devices!"
            ),
            "products": [],
            "model": "safety-guard",
        }

    # 3. Code Execution / SQL Injection / Cyberattack Material
    if re.search(
        r"(?:drop\s+table|select\s+\*\s+from|union\s+select|insert\s+into|delete\s+from|keylogger|exploit\s+script|hack\s+database)",
        norm,
    ):
        return {
            "reply": (
                "🛡️ **Action Restricted**\n\n"
                "I cannot execute arbitrary database scripts or generate cyber-exploit materials. "
                "If you are a programmer, developer, or cybersecurity researcher looking for high-performance "
                "laptops with fast multi-core CPUs and expandable RAM for development work, I would be glad to recommend top options from Dell, Asus, and Apple!"
            ),
            "products": [],
            "model": "safety-guard",
        }

    # 4. Hallucinated / Non-Existent Hardware Requests
    if re.search(
        r"(?:quantum\s+teleportation\s+phone|iphone\s+2[0-9]|1tb\s+(?:of\s+)?ram\s+for\s+10000)",
        norm,
    ):
        return {
            "reply": (
                "📱 **Catalog Verification**\n\n"
                "That specific product or specification does not correspond to genuine manufacturer hardware "
                "or our verified store catalog. EasyTech Store exclusively stocks authentic devices with valid manufacturer warranties. "
                "Feel free to explore our current collections of Apple iPhones, Samsung Galaxy devices, or high-performance laptops!"
            ),
            "products": [],
            "model": "safety-guard",
        }

    # 5. Completely Off-Topic General Trivia (Redirect to Shopping)
    if re.search(
        r"(?:who\s+won\s+the\s+2024\s+icc\s+cricket\s+world\s+cup|who\s+is\s+the\s+president\s+of|capital\s+of\s+france|write\s+(?:a\s+)?poem\s+about\s+flowers)",
        norm,
    ) and not any(k in norm for k in ["laptop", "phone", "audio", "order", "price", "buy", "cart", "product", "store", "deal"]):
        return {
            "reply": (
                "🏏 **Off-Topic Inquiry**\n\n"
                "While I enjoy trivia and sports, my primary expertise is helping you find and buy genuine electronics at EasyTech Store! 🛍️\n\n"
                "Let me know if you are looking for laptops, smartphones, headphones, smartwatches, or need help tracking an existing order."
            ),
            "products": [],
            "model": "safety-guard",
        }

    return None


# ============================================================
# STORE POLICIES, PAYMENTS, WARRANTY & ACTIONS (TIERS 6, 7 & 10)
# ============================================================

def check_store_policy_or_action_intent(
    message: str,
    user: Optional[Any] = None,
) -> Optional[Dict[str, Any]]:
    """
    Handles inquiries for:
    - Tier 6: Pincode delivery & courier carrier questions
    - Tier 7: Store return policies, refunds, warranties, GST tax invoices, payment methods, customer helpline
    - Tier 10: Cart navigation, checkout, applying coupons (SAVE10), transit damage / wrong item returns
    """
    if not message:
        return None

    norm = message.lower().strip()

    # 1. Store Return & Replacement Policy (Tier 7)
    if re.search(r"(?:return\s+policy|replacement\s+policy|can\s+i\s+return|how\s+to\s+return|opened\s+laptop\s+return|refund\s+policy|how\s+long\s+.*refund)", norm):
        return {
            "reply": (
                "🔄 **EasyTech 7-Day Replacement & Return Policy**\n\n"
                "• **Eligibility:** All eligible electronics (laptops, smartphones, audio, accessories) come with a **7-day replacement guarantee** from delivery for technical defects, transit damage, or incorrect items.\n"
                "• **Condition Guidelines:** Products must be returned with original packaging, accessories, manuals, and warranty cards. For opened laptops or phones, hardware defects are verified for instant 1:1 brand replacement.\n"
                "• **Refund Timeline:** Approved refunds are initiated immediately and processed back to your original payment method within **3–5 business days**.\n"
                "• **How to Initiate:** Simply go to your [My Orders](/orders/my-orders/) page and select *'Request Return/Replacement'* on the respective order."
            ),
            "products": [],
            "model": "store-policy",
        }

    # 2. Manufacturer Warranty & Authenticity (Tier 7)
    if re.search(r"(?:warranty|guarantee|manufacturer\s+warranty|genuine\s+product|are\s+products\s+original)", norm) and not re.search(r"(?:under|below|price|buy|show)", norm):
        return {
            "reply": (
                "🛡️ **100% Genuine Brand Warranty**\n\n"
                "• Every single product sold on EasyTech Store is **100% authentic, brand-new, and sealed**.\n"
                "• All items include the full official **Manufacturer Warranty** (typically 1–2 years for laptops, phones, monitors, and cameras).\n"
                "• You receive an official GST tax invoice with product serial numbers, honored across all authorized brand service centers in India."
            ),
            "products": [],
            "model": "store-policy",
        }

    # 3. Payment Methods & EMI (Tier 7)
    if re.search(r"(?:payment\s+method|payment\s+option|how\s+to\s+pay|accept\s+(?:upi|cod|emi|cards|paytm|gpay)|do\s+you\s+accept\s+cod|cash\s+on\s+delivery)", norm):
        return {
            "reply": (
                "💳 **Accepted Payment Methods**\n\n"
                "EasyTech Store supports safe, encrypted payment options:\n"
                "• **UPI:** Google Pay, PhonePe, Paytm, BHIM, Cred\n"
                "• **Credit & Debit Cards:** Visa, MasterCard, RuPay, American Express\n"
                "• **Net Banking:** Supported across all major Indian banks\n"
                "• **No-Cost & Low-Cost EMI:** Available on major credit cards\n"
                "• **Cash on Delivery (COD):** Available for orders up to ₹20,000\n\n"
                "All online payments are protected with 256-bit SSL encryption."
            ),
            "products": [],
            "model": "store-policy",
        }

    # 4. GST Business Invoice & ITC (Tier 7)
    if re.search(r"(?:gst\b|gst\s+invoice|business\s+invoice|tax\s+invoice|itc\b|input\s+tax\s+credit)", norm):
        return {
            "reply": (
                "🧾 **GST Tax Invoices for Business (Input Tax Credit)**\n\n"
                "• Yes! We provide full GST tax invoices for business purchases eligible for ITC.\n"
                "• When completing your order at [Checkout](/orders/checkout/), simply enter your **Company Name** and **15-digit GSTIN** in the billing section.\n"
                "• Your final downloadable invoice in [My Orders](/orders/my-orders/) will include your GSTIN with detailed HSN/SAC codes and 18%/28% GST breakdowns."
            ),
            "products": [],
            "model": "store-policy",
        }

    # 5. Human Customer Support Helpline (Tier 7)
    if re.search(r"(?:contact\s+(?:human|support|customer\s+care|help)|customer\s+care\s+number|helpline|speak\s+to\s+(?:an?\s+)?agent)", norm):
        return {
            "reply": (
                "📞 **EasyTech Customer Care & Support**\n\n"
                "Our customer support team is here to assist you:\n"
                "• **Toll-Free Helpline:** `1800-123-EASY` (1800-123-3279)\n"
                "• **Email Support:** `support@easytechstore.com`\n"
                "• **Operating Hours:** Monday to Saturday, 9:00 AM – 8:00 PM IST\n"
                "• **Self-Service:** Manage orders, track parcels, or download invoices directly in [My Orders](/orders/my-orders/)."
            ),
            "products": [],
            "model": "store-policy",
        }

    # 6. Pincode Delivery Coverage & Shipping Logistics (Tier 6)
    if re.search(r"(?:deliver\s+to\s+pincode|deliver\s+to\s+\d{6}|shipping\s+coverage|shipping\s+time|how\s+long\s+to\s+deliver)", norm):
        pincode_match = re.search(r"\b(\d{6})\b", norm)
        pincode_str = f" to pincode **{pincode_match.group(1)}**" if pincode_match else ""
        return {
            "reply": (
                f"🚚 **Shipping Coverage & Transit Estimates**\n\n"
                f"• EasyTech delivers{pincode_str} across 25,000+ pincodes in India via express logistics partners (**BlueDart**, **Delhivery**, **DTDC**).\n"
                "• **Metro Cities:** 1–2 business days\n"
                "• **Tier 2 & 3 Cities:** 2–4 business days\n"
                "• **Prepaid Orders:** Enjoy **FREE Express Delivery** on all orders over ₹999!"
            ),
            "products": [],
            "model": "store-policy",
        }

    # 7. Cart, Checkout & Coupon Actions (Tier 10)
    if re.search(r"(?:how\s+do\s+i\s+view\s+my\s+(?:shopping\s+)?cart|view\s+(?:my\s+)?(?:shopping\s+)?cart|go\s+to\s+cart|proceed\s+to\s+checkout|how\s+to\s+checkout|apply\s+coupon|save10)", norm):
        return {
            "reply": (
                "🛒 **Cart & Checkout Quick Actions**\n\n"
                "• **View Cart:** Review your selected products anytime at [My Shopping Cart](/cart/).\n"
                "• **Proceed to Checkout:** Go straight to the secure [Checkout Page](/orders/checkout/) to select shipping address and payment method.\n"
                "• **Applying Coupon SAVE10:** On the checkout summary screen, enter promo code **SAVE10** in the coupon field and click *'Apply'* to receive an instant 10% discount on eligible electronics!"
            ),
            "products": [],
            "model": "action-request",
        }

    # 8. Transit Damage & Wrong Product Resolution (Tier 10)
    if re.search(r"(?:wrong\s+product|cracked\s+screen|damaged\s+product|damaged\s+laptop|defective\s+product|received\s+damaged)", norm):
        return {
            "reply": (
                "⚠️ **Damaged or Incorrect Product Assistance**\n\n"
                "We sincerely apologize for the inconvenience! EasyTech provides immediate resolution:\n\n"
                "1. Go to your [My Orders](/orders/my-orders/) dashboard.\n"
                "2. Click on the affected order and select **'Report Transit Damage / Wrong Item'**.\n"
                "3. Upload clear photos of the damaged item and outer packaging box.\n"
                "4. Our support team will dispatch a **free 1:1 replacement** within 24–48 hours and coordinate courier doorstep pickup."
            ),
            "products": [],
            "model": "action-request",
        }

    return None


# ============================================================
# MULTI-TURN QUERY CONDENSATION (REWRITER)
# ============================================================

def condense_query_with_history(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
) -> str:
    """
    Given multi-turn conversation history, condense/rewrite follow-up queries
    (e.g., "What about under 5000?", "Is it in stock?", "Show wireless ones", "Show options from Asus instead")
    into a standalone product search query suitable for semantic & catalog retrieval.
    """
    if not history:
        return message

    recent = [h for h in history if h.get("content")][-4:]
    if not recent:
        return message

    # 1. Attempt LLM-based query rewrite with fast timeout
    try:
        client, primary_model, fallback_model = get_llm_client_and_models(timeout_override=3.5)

        history_summary = []
        for h in recent:
            role = "Customer" if h.get("role") == "user" else "Assistant"
            content = h.get("content", "").strip()
            if len(content) > 100:
                content = content[:100] + "..."
            history_summary.append(f"{role}: {content}")

        rewrite_prompt = (
            "You are a search query optimizer for an electronics store.\n"
            "Given the conversation history and customer's follow-up question, "
            "rephrase the customer's follow-up question into a single concise standalone search query. "
            "Include product type, brand, and constraints (e.g. price, brand change, or hardware features). "
            "Output ONLY the search query text without quotes or explanations.\n\n"
            "Conversation History:\n"
            + "\n".join(history_summary)
            + f"\n\nCustomer follow-up: {message}\n"
            "Standalone Search Query:"
        )

        try:
            resp = client.chat.completions.create(
                model=primary_model,
                messages=[{"role": "user", "content": rewrite_prompt}],
                temperature=0.0,
                max_tokens=30,
            )
        except Exception:
            resp = client.chat.completions.create(
                model=fallback_model,
                messages=[{"role": "user", "content": rewrite_prompt}],
                temperature=0.0,
                max_tokens=30,
            )

        condensed = resp.choices[0].message.content.strip().strip('"').strip("'")
        if condensed and len(condensed) < 150 and not condensed.lower().startswith("i "):
            logger.info("Rewrote multi-turn query '%s' -> '%s'", message, condensed)
            return condensed

    except Exception as exc:
        logger.debug("Query condensation via LLM skipped or timed out: %s", exc)

    # 2. Heuristic fallback: combine context from previous user turn if query is short
    last_user_msg = next((h["content"] for h in reversed(recent) if h.get("role") == "user"), "")
    if last_user_msg and len(message.split()) <= 6:
        detected_cat = detect_category(last_user_msg)
        detected_brands = detect_brands(last_user_msg)
        context_tokens = []
        # Check if user is switching brand explicitly
        new_brand = detect_brands(message)
        if new_brand:
            context_tokens.extend(new_brand)
        elif detected_brands:
            context_tokens.extend(detected_brands)

        if detected_cat and not detect_category(message):
            context_tokens.append(detected_cat)

        if context_tokens:
            combined = " ".join(context_tokens) + " " + message
            logger.info("Heuristic condensed query: '%s' -> '%s'", message, combined)
            return combined

    return message


# ============================================================
# HISTORICAL CHAT KNOWLEDGE & CONTINUOUS LEARNING MEMORY
# ============================================================

def retrieve_historical_chat_knowledge(
    query: str,
    user: Optional[Any] = None,
    limit: int = 3,
) -> List[Dict[str, str]]:
    """
    Retrieves high-quality past chat Q&A interactions and customer conversation memory
    (e.g., messages with thumbs_up rating, or relevant previous bot answers) to use
    as dynamic in-context knowledge for the chatbot.
    """
    from chatbot.models import ChatMessage

    knowledge_pairs = []
    seen_answers = set()

    try:
        keywords = extract_search_keywords(query)

        # 1. Look for highly-rated previous bot responses (thumbs_up)
        thumbs_up_msgs = (
            ChatMessage.objects
            .filter(sender="bot", rating="thumbs_up")
            .exclude(message__startswith="Hi! ")
            .order_by("-created_at")
        )

        for bot_m in thumbs_up_msgs[:20]:
            # Find the user query directly preceding this bot response
            prior_user_msg = (
                ChatMessage.objects
                .filter(
                    session_key=bot_m.session_key,
                    sender="user",
                    created_at__lt=bot_m.created_at
                )
                .order_by("-created_at")
                .first()
            )
            if not prior_user_msg and bot_m.user:
                prior_user_msg = (
                    ChatMessage.objects
                    .filter(
                        user=bot_m.user,
                        sender="user",
                        created_at__lt=bot_m.created_at
                    )
                    .order_by("-created_at")
                    .first()
                )

            if prior_user_msg and prior_user_msg.message:
                u_text = prior_user_msg.message.strip()
                b_text = bot_m.message.strip()

                # Check relevance to current query keywords or category
                matches = sum(1 for kw in keywords if kw.lower() in u_text.lower() or kw.lower() in b_text.lower())
                if matches > 0 or not keywords:
                    if b_text not in seen_answers:
                        knowledge_pairs.append({
                            "question": u_text,
                            "answer": b_text,
                            "source": "verified_thumbs_up_chat",
                        })
                        seen_answers.add(b_text)
                        if len(knowledge_pairs) >= limit:
                            break

        # 2. Extract personalized user past context if user is authenticated
        if user and getattr(user, "is_authenticated", False) and len(knowledge_pairs) < limit:
            user_past = (
                ChatMessage.objects
                .filter(user=user, sender="user")
                .exclude(message=query)
                .order_by("-created_at")[:5]
            )
            past_queries = [m.message for m in user_past if len(m.message) > 5]
            if past_queries:
                knowledge_pairs.append({
                    "question": "Customer's previous search topics",
                    "answer": ", ".join(past_queries[:3]),
                    "source": "user_interaction_memory",
                })

    except Exception as exc:
        logger.debug("Error retrieving historical chat knowledge: %s", exc)

    return knowledge_pairs


# ============================================================
# CHAT RESPONSE GENERATION (10-TIER GROUNDED & TRAINED)
# ============================================================

def generate_chat_response(
    message: str,
    history: Optional[List[Dict[str, str]]] = None,
    user: Optional[Any] = None,
) -> Dict[str, Any]:

    if not message or not message.strip():
        return {
            "reply": "Hi! 👋 What electronics product are you looking for today?",
            "products": [],
            "model": OLLAMA_MODEL,
        }

    # 0A. TIER 9: SAFETY, ANTI-HALLUCINATION & JAILBREAK GUARD
    safety_res = check_safety_guard(message)
    if safety_res:
        return safety_res

    # 0B. TIER 6: ORDER TRACKING INTENT DETECTION
    order_tracking_res = check_order_tracking_intent(message, user=user)
    if order_tracking_res:
        return order_tracking_res

    # 0C. TIERS 6, 7 & 10: STORE POLICIES, WARRANTIES, PAYMENTS & QUICK ACTIONS
    policy_res = check_store_policy_or_action_intent(message, user=user)
    if policy_res:
        return policy_res

    # 1. MULTI-TURN QUERY CONDENSATION & RETRIEVAL (TIERS 1, 2, 3, 5, 8)
    search_query = condense_query_with_history(message, history=history) if history else message
    products = retrieve_relevant_products(search_query, n_results=6)

    # 1B. HISTORICAL CHAT KNOWLEDGE RETRIEVAL (CONTINUOUS LEARNING MEMORY)
    historical_knowledge = retrieve_historical_chat_knowledge(search_query, user=user, limit=2)
    history_knowledge_prompt = ""
    if historical_knowledge:
        hk_lines = []
        for item in historical_knowledge:
            if item.get("source") == "verified_thumbs_up_chat":
                hk_lines.append(f"• Verified Customer Q: \"{item['question']}\" -> Answered: \"{item['answer'][:160]}...\"")
            elif item.get("source") == "user_interaction_memory":
                hk_lines.append(f"• Customer's Past Interest Context: {item['answer']}")
        if hk_lines:
            history_knowledge_prompt = "\nLEARNED HISTORICAL CHAT KNOWLEDGE (VERIFIED PAST STORE INTERACTIONS):\n" + "\n".join(hk_lines) + "\n"

    # 2. PREPARE CATALOG CONTEXT
    if products:
        context_items = "\n".join([
            (
                f"{index}. Product: {p.get('name', 'Product')} | "
                f"Brand: {p.get('brand', 'Generic')} | "
                f"Category: {p.get('category', 'Electronics')} | "
                f"Price: ₹{float(p.get('price', 0)):,.2f} | "
                f"Stock: {p.get('stock', 0)} units | "
                f"Description: {p.get('description') or 'Official store model'} | "
                f"Specifications: {p.get('specifications') or 'Standard manufacturer specs'} | "
                f"Link: {p.get('url', '#')}"
            )
            for index, p in enumerate(products, start=1)
        ])

        context_prompt = f"""
STRICT VERIFIED STORE CATALOG DATA:
{context_items}

CRITICAL ANTI-HALLUCINATION INSTRUCTIONS:
- ONLY state specifications explicitly listed above.
- NEVER invent unverified hardware details (like specific GPU models RTX 3070, RAM sizes 16GB/32GB, or SSD capacities 512GB/1TB) unless they appear in the catalog text above.
- If a customer asks for a specific spec (e.g. 16GB RAM or 512GB SSD) not explicitly detailed in the description, state the matching model available in that category and invite them to view the product link for the full manufacturer spec sheet.
- Quote prices accurately in Indian Rupees (₹).
"""
    else:
        context_prompt = """
NO MATCHING PRODUCTS FOUND IN CATALOG.
State politely that we don't have that exact model, spec, or price range in stock right now and invite the customer to browse our other categories.
"""

    few_shot_examples = """
FEW-SHOT EXAMPLES (10-TIER EVALUATION GROUNDING):

[Tier 1: Price & Budget Parsing]
Customer: "Show me laptops under 50000"
Assistant: "Here are our top laptops under ₹50,000! We have the **Dell Inspiron 15** for **₹42,990** and **HP 15s** for **₹47,490**. Both are great for productivity and office work. You can view all options below!"

[Tier 2: Brand & Category Isolation]
Customer: "Do you have any Apple tablets or iPads under ₹35,000?"
Assistant: "Yes! We have the **Apple iPad 9th Gen (64GB, Wi-Fi)** in stock for **₹30,900**. It features a 10.2-inch Retina display and the A13 Bionic chip, making it a great tablet for everyday work and entertainment. You can view the full specifications and order directly from the product card below!"

[Tier 3: Hardware Specifications]
Customer: "Laptops with 16GB RAM and 512GB SSD"
Assistant: "We have the **Asus ZenBook 14** featuring **16GB LPDDR5 RAM** and a fast **512GB PCIe NVMe SSD** for **₹78,990**. It delivers exceptional multitasking performance and rapid load times. Check out the product card below for complete specs!"

[Tier 4: Comparative Decision Making]
Customer: "Compare Apple MacBook Air and Dell XPS 13"
Assistant: "Here is a comparison between the two premium ultrabooks:
• **Apple MacBook Air (M2)**: Unbeatable battery life (up to 18 hrs), silent fanless operation, and Apple Silicon efficiency (₹94,900).
• **Dell XPS 13**: High-resolution InfinityEdge display, Windows 11 compatibility, and Intel Core i7 performance (₹1,09,900).
If you prefer battery endurance and macOS, go with the MacBook Air; if you need Windows software compatibility and display sharpness, the Dell XPS 13 is the winner!"

[Tier 5: Multi-Turn Dialogue & Pronoun Resolution]
Customer: "What about under 50k?" (After discussing Laptops)
Assistant: "Looking at laptops under ₹50,000, we recommend the **Dell Inspiron 15** at **₹42,990** (Intel Core i3, 8GB RAM, 512GB SSD). It offers reliable daily productivity and great battery life!"

[Tier 8: Slang, Hinglish & Typo Tolerance]
Customer: "Mobiles under 20 hazaar"
Assistant: "Here are top smartphones under ₹20,000! We have the **Samsung Galaxy M34** starting at **₹16,990** featuring a vibrant Super AMOLED display and long-lasting 6000mAh battery. Explore the product cards below!"
"""

    system_prompt = f"""
You are 'EasyTech Assistant', the official AI shopping consultant for EasyTech Store.

CRITICAL RULES (100% CATALOG CONSISTENCY & ANTI-HALLUCINATION):
1. Ground every statement strictly in the provided STORE CATALOG DATA below.
2. ONLY mention and recommend the products listed in the STORE CATALOG DATA. NEVER invent or name unlisted brands or models.
3. Present the matching products from the catalog with their exact names, brands, and prices in Indian Rupees (₹).
4. If NO matching products are found in the catalog below, politely state that we don't have matching models in stock right now and invite the customer to browse other categories.
5. Keep responses concise, helpful, and friendly.
6. If the user asks about order tracking, explain that they can track orders anytime with 'Track order #<order_id>' or via their 'My Orders' dashboard.

{few_shot_examples}

{history_knowledge_prompt}

{context_prompt}
"""

    try:
        client, primary_model, fallback_model = get_llm_client_and_models()

        messages = [{"role": "system", "content": system_prompt}]

        if history:
            for item in history[-6:]:
                role = item.get("role", "user")
                content = item.get("content", "")
                if role in ("user", "assistant") and content:
                    messages.append({"role": role, "content": content})

        messages.append({"role": "user", "content": message})

        used_model = primary_model
        try:
            response = client.chat.completions.create(
                model=primary_model,
                messages=messages,
                temperature=0.0,  # Zero temperature for maximum factual consistency
                max_tokens=350,
            )
        except Exception as model_exc:
            if fallback_model and fallback_model != primary_model:
                logger.warning(
                    "Primary model %s failed (%s), attempting fallback to %s",
                    primary_model,
                    model_exc,
                    fallback_model,
                )
                used_model = fallback_model
                response = client.chat.completions.create(
                    model=fallback_model,
                    messages=messages,
                    temperature=0.0,
                    max_tokens=350,
                )
            else:
                raise model_exc

        reply_text = response.choices[0].message.content.strip()

        return {
            "reply": reply_text,
            "products": products,
            "model": used_model,
        }

    except Exception as exc:
        logger.exception("Error communicating with AI service (%s): %s", primary_model if 'primary_model' in locals() else 'LLM', exc)

        if products:
            product_list_str = "\n".join([
                f"- **{p['name']}** ({p['brand']}): ₹{p['price']:,.2f} ({p['stock']} in stock)"
                for p in products
            ])
            fallback_message = (
                f"Here are the best matching products from our catalog:\n\n{product_list_str}"
            )
        else:
            fallback_message = (
                "Sorry, I couldn't find a matching product in the EasyTech Store catalog. "
                "Please try another product, brand, category, or price range."
            )

        return {
            "reply": fallback_message,
            "products": products,
            "model": "catalog-fallback",
            "error": str(exc),
        }