import io
import csv
import re
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.db.models import Count

from products.models import Brand
from category.models import Category
from .decorators import manager_required


@manager_required
def manager_brands(request):
    """Display list of all brands with associated categories and product counts"""
    brands = Brand.objects.prefetch_related('categories').annotate(product_count=Count('products')).order_by('name')
    context = {'brands': brands}
    return render(request, 'manager/brands.html', context)


@manager_required
def brand_add(request):
    """Create a new brand and associate categories"""
    categories = Category.objects.filter(is_active=True).order_by('name')
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            selected_category_ids = request.POST.getlist('categories')
            
            if not name:
                messages.error(request, "Brand name is required.")
                return render(request, 'manager/brand_add.html', {'categories': categories})
            
            if Brand.objects.filter(name__iexact=name).exists():
                messages.error(request, f"A brand with name '{name}' already exists.")
                return render(request, 'manager/brand_add.html', {'categories': categories})
            
            brand = Brand(name=name, description=description)
            brand.save()
            if selected_category_ids:
                brand.categories.set(selected_category_ids)
            
            messages.success(request, f"Brand '{name}' created successfully!")
            return redirect('manager:brands')
            
        except Exception as e:
            messages.error(request, f"Error creating brand: {str(e)}")
            return render(request, 'manager/brand_add.html', {'categories': categories})
    
    return render(request, 'manager/brand_add.html', {'categories': categories})


@manager_required
def brand_edit(request, pk):
    """Edit an existing brand and update categories"""
    brand = get_object_or_404(Brand.objects.prefetch_related('categories'), pk=pk)
    categories = Category.objects.filter(is_active=True).order_by('name')
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', brand.name).strip()
            description = request.POST.get('description', brand.description).strip()
            selected_category_ids = request.POST.getlist('categories')
            
            if not name:
                messages.error(request, "Brand name cannot be empty.")
                return render(request, 'manager/brand_edit.html', {'brand': brand, 'categories': categories})
            
            if Brand.objects.filter(name__iexact=name).exclude(pk=brand.pk).exists():
                messages.error(request, f"Another brand with name '{name}' already exists.")
                return render(request, 'manager/brand_edit.html', {'brand': brand, 'categories': categories})
            
            brand.name = name
            brand.description = description
            brand.save()
            brand.categories.set(selected_category_ids)
            
            messages.success(request, f"Brand '{brand.name}' updated successfully!")
            return redirect('manager:brands')
            
        except Exception as e:
            messages.error(request, f"Error updating brand: {str(e)}")
    
    context = {'brand': brand, 'categories': categories}
    return render(request, 'manager/brand_edit.html', context)


@manager_required
def brand_delete(request, pk):
    """Delete a brand"""
    brand = get_object_or_404(Brand.objects.annotate(product_count=Count('products')), pk=pk)
    
    if request.method == 'POST':
        brand_name = brand.name
        brand.delete()
        messages.success(request, f"Brand '{brand_name}' deleted successfully!")
        return redirect('manager:brands')
    
    context = {'brand': brand}
    return render(request, 'manager/brand_confirm_delete.html', context)


@manager_required
def brand_import(request):
    """Bulk import brands and associate them with categories from uploaded Excel (.xlsx, .xls) or CSV (.csv) file"""
    if request.method == 'POST':
        uploaded_file = request.FILES.get('excel_file')
        if not uploaded_file:
            messages.error(request, "Please select an Excel (.xlsx) or CSV file to upload.")
            return render(request, 'manager/brand_import.html')

        filename = uploaded_file.name.lower()
        created_count = 0
        already_exists_count = 0
        skipped_count = 0
        linked_categories_count = 0

        try:
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
                    messages.error(
                        request,
                        "Excel (.xlsx) parser 'openpyxl' is not installed in the server environment. Please upload a CSV (.csv) file instead or install 'openpyxl'."
                    )
                    return render(request, 'manager/brand_import.html')
            else:
                messages.error(request, "Unsupported file format. Please upload an Excel (.xlsx) or CSV (.csv) file.")
                return render(request, 'manager/brand_import.html')

            if not rows or len(rows) < 2:
                messages.error(request, "The uploaded file is empty or missing data rows (minimum 1 header + 1 data row required).")
                return render(request, 'manager/brand_import.html')

            headers = [str(h).strip().lower() for h in rows[0]]
            name_idx = -1
            category_idx = -1
            desc_idx = -1

            for idx, h in enumerate(headers):
                if 'brand' in h or 'manufacturer' in h or ('name' in h and 'cat' not in h):
                    name_idx = idx
                elif 'category' in h or 'catory' in h or 'categories' in h or 'dept' in h:
                    category_idx = idx
                elif 'desc' in h or 'detail' in h or 'info' in h:
                    desc_idx = idx

            if name_idx == -1:
                name_idx = 0
            if category_idx == -1 and len(headers) > 1:
                category_idx = 1
            if desc_idx == -1 and len(headers) > 2:
                desc_idx = 2

            for row in rows[1:]:
                if not row or not any(row):
                    continue

                name = str(row[name_idx]).strip() if len(row) > name_idx else ""
                category_str = str(row[category_idx]).strip() if (category_idx != -1 and len(row) > category_idx) else ""
                desc = str(row[desc_idx]).strip() if (desc_idx != -1 and len(row) > desc_idx) else ""

                if not name:
                    skipped_count += 1
                    continue

                brand = Brand.objects.filter(name__iexact=name).first()
                if brand:
                    already_exists_count += 1
                else:
                    brand = Brand.objects.create(name=name, description=desc)
                    created_count += 1

                if category_str:
                    category_names = [c.strip() for c in re.split(r'[,;/|]+', category_str) if c.strip()]
                    for cat_name in category_names:
                        category_obj, _ = Category.objects.get_or_create(
                            name__iexact=cat_name,
                            defaults={'name': cat_name, 'is_active': True}
                        )
                        if not brand.categories.filter(id=category_obj.id).exists():
                            brand.categories.add(category_obj)
                            linked_categories_count += 1

            if created_count > 0:
                msg = f"Bulk brand import completed successfully! Created {created_count} new brands and mapped {linked_categories_count} category associations."
                if already_exists_count > 0:
                    msg += f" {already_exists_count} existing brands were preserved without being overwritten."
                messages.success(request, msg)
                return redirect('manager:brands')
            elif already_exists_count > 0:
                messages.info(
                    request,
                    f"Brand import completed: {already_exists_count} existing brands were preserved without being overwritten, and {linked_categories_count} category associations were linked."
                )
                return redirect('manager:brands')
            else:
                messages.warning(request, "No valid brand names found in the uploaded file.")

        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")

    return render(request, 'manager/brand_import.html')


@manager_required
def brand_sample_template(request):
    """Generates and downloads a sample file (Excel .xlsx or CSV .csv) for bulk brand import"""
    format_type = request.GET.get('format', '').strip().lower()

    sample_rows = [
        ["Brand Name", "Category", "Description"],
        ["Apple", "Laptops, Smartphones, Smartwatches, Audio & Headphones", "Premium electronics, iPhones, MacBooks, Apple Watch, and AirPods"],
        ["Dell", "Laptops, Monitors & Displays, Computer Accessories", "High performance XPS ultrabooks, Inspiron laptops, and UltraSharp monitors"],
        ["Samsung", "Smartphones, Monitors & Displays, Smartwatches", "Galaxy smartphones, Galaxy Watches, and Odyssey OLED gaming monitors"],
        ["Sony", "Audio & Headphones, Gaming Consoles", "PlayStation consoles, WH-1000XM5 wireless noise cancelling headphones"],
        ["HP", "Laptops, Monitors & Displays, Computer Accessories", "Spectre ultrabooks, Omen gaming laptops, and computer accessories"],
        ["Logitech", "Keyboards & Mice, Computer Accessories", "Master series mice, mechanical keyboards, streamcams, and USB accessories"],
        ["Asus", "Laptops, Monitors & Displays, Keyboards & Mice", "ROG gaming laptops, ZenBook ultrabooks, and gaming peripherals"],
        ["Bose", "Audio & Headphones", "QuietComfort wireless noise cancelling headphones and premium audio systems"],
    ]

    if format_type == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        for row in sample_rows:
            writer.writerow(row)
        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="easytech_brands_template.csv"'
        return response

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Brands"

        ws.append(sample_rows[0])
        header_fill = PatternFill(start_color="1E40AF", end_color="1E40AF", fill_type="solid")
        header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")

        for col_num in range(1, 4):
            cell = ws.cell(row=1, column=col_num)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        for row in sample_rows[1:]:
            ws.append(row)

        ws.column_dimensions['A'].width = 22
        ws.column_dimensions['B'].width = 45
        ws.column_dimensions['C'].width = 65

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="easytech_brands_template.xlsx"'
        return response

    except (ImportError, Exception):
        output = io.StringIO()
        writer = csv.writer(output)
        for row in sample_rows:
            writer.writerow(row)
        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="easytech_brands_template.csv"'
        return response
