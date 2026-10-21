import io
import os
import csv
import json
import re
import urllib.request
from urllib.parse import urlparse
from django.core.files.base import ContentFile
from django.http import HttpResponse

from products.models import Product, Brand
from category.models import Category


def parse_product_spreadsheet_rows(uploaded_file):
    """Parses an uploaded Excel (.xlsx, .xls) or CSV (.csv) file into a list of cleaned product dictionaries"""
    filename = uploaded_file.name.lower()
    rows = []
    if filename.endswith('.csv'):
        decoded_file = uploaded_file.read().decode('utf-8-sig').splitlines()
        reader = csv.reader(decoded_file)
        rows = list(reader)
    elif filename.endswith(('.xlsx', '.xls')):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(uploaded_file, data_only=True)
            sheet = wb.active
            for row in sheet.iter_rows(values_only=True):
                if any(row):
                    rows.append([str(cell) if cell is not None else "" for cell in row])
        except ImportError:
            raise ValueError("Excel (.xlsx) parser 'openpyxl' is not installed in the server environment. Please upload a CSV (.csv) file instead or install 'openpyxl'.")
    else:
        raise ValueError("Unsupported file format. Please upload an Excel (.xlsx) or CSV (.csv) file.")

    if not rows or len(rows) < 2:
        raise ValueError("The uploaded file is empty or missing data rows (minimum 1 header + 1 data row required).")

    headers = [str(h).strip().lower() for h in rows[0]]
    name_idx = -1
    category_idx = -1
    brand_idx = -1
    price_idx = -1
    discount_idx = -1
    stock_idx = -1
    photo_idx = -1
    specs_idx = -1
    desc_idx = -1
    active_idx = -1

    for idx, h in enumerate(headers):
        if 'product' in h or ('name' in h and 'cat' not in h and 'brand' not in h):
            name_idx = idx
        elif 'category' in h or 'catory' in h:
            category_idx = idx
        elif 'brand' in h or 'manufacturer' in h:
            brand_idx = idx
        elif 'price' in h or 'cost' in h or 'mrp' in h:
            price_idx = idx
        elif 'discount' in h or 'off' in h:
            discount_idx = idx
        elif 'stock' in h or 'qty' in h or 'quantity' in h:
            stock_idx = idx
        elif 'photo' in h or 'image' in h or 'picture' in h or 'img' in h or 'pic' in h:
            photo_idx = idx
        elif 'spec' in h or 'detail' in h:
            specs_idx = idx
        elif 'desc' in h or 'info' in h:
            desc_idx = idx
        elif 'active' in h or 'status' in h or 'enable' in h:
            active_idx = idx

    if name_idx == -1:
        name_idx = 0
    if category_idx == -1 and len(headers) > 1:
        category_idx = 1
    if price_idx == -1 and len(headers) > 3:
        price_idx = 3

    parsed_items = []
    for row in rows[1:]:
        if not row or not any(row):
            continue

        name = str(row[name_idx]).strip() if len(row) > name_idx else ""
        if not name:
            continue

        category_name = str(row[category_idx]).strip() if (category_idx != -1 and len(row) > category_idx) else ""
        brand_name = str(row[brand_idx]).strip() if (brand_idx != -1 and len(row) > brand_idx) else ""
        price_str = str(row[price_idx]).strip() if (price_idx != -1 and len(row) > price_idx) else "0"
        discount_str = str(row[discount_idx]).strip() if (discount_idx != -1 and len(row) > discount_idx) else "0"
        stock_str = str(row[stock_idx]).strip() if (stock_idx != -1 and len(row) > stock_idx) else "0"
        photo_str = str(row[photo_idx]).strip() if (photo_idx != -1 and len(row) > photo_idx) else ""
        specs = str(row[specs_idx]).strip() if (specs_idx != -1 and len(row) > specs_idx) else ""
        desc = str(row[desc_idx]).strip() if (desc_idx != -1 and len(row) > desc_idx) else ""
        active_str = str(row[active_idx]).strip().lower() if (active_idx != -1 and len(row) > active_idx) else "yes"

        try:
            price_val = float(re.sub(r'[^\d.]', '', price_str) or 0)
        except (ValueError, TypeError):
            price_val = 0.0

        try:
            discount_val = float(re.sub(r'[^\d.]', '', discount_str) or 0)
        except (ValueError, TypeError):
            discount_val = 0.0

        try:
            stock_val = int(float(re.sub(r'[^\d.]', '', stock_str) or 0))
        except (ValueError, TypeError):
            stock_val = 0

        is_active = active_str not in ['no', 'false', '0', 'inactive', 'off']

        parsed_items.append({
            'name': name,
            'category': category_name or 'General',
            'brand': brand_name,
            'price': price_val,
            'discount': discount_val,
            'stock': stock_val,
            'photo_url': photo_str,
            'specifications': specs,
            'description': desc,
            'is_active': is_active
        })

    return parsed_items


def _is_safe_image_url(url: str) -> bool:
    """Blocks SSRF attacks targeting private networks, loopback, or AWS metadata (169.254.169.254)."""
    try:
        import ipaddress
        import socket
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https'):
            return False
        hostname = (parsed.hostname or '').strip().lower()
        if not hostname:
            return False
        blocked = {'localhost', '127.0.0.1', '169.254.169.254', '0.0.0.0', '::1', 'metadata.google.internal'}
        if hostname in blocked or '169.254' in hostname:
            return False
        try:
            ip_str = socket.gethostbyname(hostname)
            ip_obj = ipaddress.ip_address(ip_str)
            if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local or ip_obj.is_reserved:
                return False
        except Exception:
            return False
        return True
    except Exception:
        return False


def _attach_photo_to_product(product_obj, photo_str, name):
    """Helper to download and attach an image from URL or local media path."""
    if not photo_str:
        return False

    from django.conf import settings
    try:
        media_products_dir = os.path.join(settings.MEDIA_ROOT, 'products')
        os.makedirs(media_products_dir, exist_ok=True)
    except Exception:
        pass

    if photo_str.startswith(('http://', 'https://')):
        if not _is_safe_image_url(photo_str):
            import logging
            logging.getLogger(__name__).warning("Blocked unsafe SSRF image URL for '%s': %s", name, photo_str)
            return False
        try:
            req = urllib.request.Request(
                photo_str,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    img_data = resp.read(10 * 1024 * 1024 + 1)
                    if len(img_data) > 10 * 1024 * 1024:
                        return False
                    content_type = (resp.headers.get('Content-Type') or '').lower()
                    if 'jpeg' in content_type or 'jpg' in content_type:
                        ext = '.jpg'
                    elif 'png' in content_type:
                        ext = '.png'
                    elif 'webp' in content_type:
                        ext = '.webp'
                    elif 'gif' in content_type:
                        ext = '.gif'
                    else:
                        parsed = urlparse(photo_str)
                        path_part = parsed.path.split('/')[-1]
                        ext = os.path.splitext(path_part)[1].lower() if '.' in path_part else '.jpg'
                        if ext not in ['.jpg', '.jpeg', '.png', '.webp', '.gif']:
                            ext = '.jpg'

                    safe_slug = re.sub(r'[^a-zA-Z0-9_]', '_', name.lower())[:40]
                    filename = f"{safe_slug}{ext}"
                    image_file = ContentFile(img_data, name=filename)
                    product_obj.image.save(filename, image_file, save=False)
                    return True
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("Failed to download image for '%s' from %s: %s", name, photo_str, exc)
            return False
    else:
        clean_photo = photo_str.lstrip('/')
        if clean_photo.startswith('media/'):
            clean_photo = clean_photo[6:]
        product_obj.image = clean_photo
        return True
    return False


def save_single_imported_product(data):
    """Saves or checks an individual imported product, downloads photo, links category and brand"""
    name = str(data.get('name', '')).strip()
    if not name:
        return {'status': 'skipped', 'name': '', 'message': 'Empty product name'}

    # 1. Check if product already exists
    existing_product = Product.objects.filter(name__iexact=name).first()
    if existing_product:
        photo_str = str(data.get('photo_url', '')).strip()
        has_valid_image = False
        if existing_product.image and existing_product.image.name:
            try:
                has_valid_image = os.path.exists(existing_product.image.path)
            except Exception:
                has_valid_image = False

        # If product already exists but has no valid image, and photo_url is provided, attach the image!
        if photo_str and not has_valid_image:
            attached = _attach_photo_to_product(existing_product, photo_str, name)
            if attached:
                existing_product.save()
                return {
                    'status': 'updated',
                    'name': name,
                    'message': f"Product '{name}' already existed; updated missing photo from URL."
                }
        return {
            'status': 'already_exists',
            'name': name,
            'message': f"Product '{name}' already exists (preserved without overwriting)."
        }

    category_name = str(data.get('category', '')).strip() or 'General'
    brand_name = str(data.get('brand', '')).strip()
    price_val = float(data.get('price', 0) or 0)
    discount_val = float(data.get('discount', 0) or 0)
    stock_val = int(data.get('stock', 0) or 0)
    photo_str = str(data.get('photo_url', '')).strip()
    specs = str(data.get('specifications', '')).strip()
    desc = str(data.get('description', '')).strip()
    is_active = bool(data.get('is_active', True))

    cat_obj, _ = Category.objects.get_or_create(
        name__iexact=category_name,
        defaults={'name': category_name, 'is_active': True}
    )

    brand_obj = None
    if brand_name:
        brand_obj, _ = Brand.objects.get_or_create(
            name__iexact=brand_name,
            defaults={'name': brand_name}
        )
        if not brand_obj.categories.filter(id=cat_obj.id).exists():
            brand_obj.categories.add(cat_obj)

    product_obj = Product(
        name=name,
        category=cat_obj,
        brand=brand_obj,
        price=price_val,
        discount=discount_val,
        stock=stock_val,
        specifications=specs,
        description=desc,
        is_active=is_active
    )

    if photo_str:
        _attach_photo_to_product(product_obj, photo_str, name)

    product_obj.save()
    return {
        'status': 'created',
        'name': name,
        'category': cat_obj.name,
        'brand': brand_obj.name if brand_obj else None,
        'message': f"Product '{name}' created successfully!"
    }
