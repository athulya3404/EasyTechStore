import io
import csv
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib import messages
from django.db.models import Count

from category.models import Category
from .decorators import manager_required


@manager_required
def manager_categories(request):
    """Display list of all categories with product counts and associated brands"""
    categories = Category.objects.prefetch_related('brands').annotate(product_count=Count('products')).order_by('name')
    context = {'categories': categories}
    return render(request, 'manager/categories.html', context)


@manager_required
def category_add(request):
    """Create a new category"""
    if request.method == 'POST':
        try:
            name = request.POST.get('name', '').strip()
            description = request.POST.get('description', '').strip()
            is_active = request.POST.get('is_active') == 'on' or 'is_active' not in request.POST
            
            if not name:
                messages.error(request, "Category name is required.")
                return render(request, 'manager/category_add.html')
            
            if Category.objects.filter(name__iexact=name).exists():
                messages.error(request, f"A category with name '{name}' already exists.")
                return render(request, 'manager/category_add.html')
            
            category = Category(name=name, description=description, is_active=is_active)
            category.save()
            
            messages.success(request, f"Category '{name}' created successfully!")
            return redirect('manager:categories')
            
        except Exception as e:
            messages.error(request, f"Error creating category: {str(e)}")
            return render(request, 'manager/category_add.html')
    
    return render(request, 'manager/category_add.html')


@manager_required
def category_edit(request, pk):
    """Edit an existing category"""
    category = get_object_or_404(Category, pk=pk)
    
    if request.method == 'POST':
        try:
            name = request.POST.get('name', category.name).strip()
            description = request.POST.get('description', category.description).strip()
            is_active = request.POST.get('is_active') == 'on'
            
            if not name:
                messages.error(request, "Category name cannot be empty.")
                return render(request, 'manager/category_edit.html', {'category': category})
            
            if Category.objects.filter(name__iexact=name).exclude(pk=category.pk).exists():
                messages.error(request, f"Another category with name '{name}' already exists.")
                return render(request, 'manager/category_edit.html', {'category': category})
            
            category.name = name
            category.description = description
            category.is_active = is_active
            category.save()
            
            messages.success(request, f"Category '{category.name}' updated successfully!")
            return redirect('manager:categories')
            
        except Exception as e:
            messages.error(request, f"Error updating category: {str(e)}")
    
    context = {'category': category}
    return render(request, 'manager/category_edit.html', context)


@manager_required
def category_delete(request, pk):
    """Delete a category with safety checks"""
    category = get_object_or_404(Category.objects.annotate(product_count=Count('products')), pk=pk)
    
    if request.method == 'POST':
        if category.products.exists():
            messages.error(request, f"Cannot delete category '{category.name}' because it contains {category.products.count()} active product(s). Reassign or delete the products first.")
            return redirect('manager:categories')
            
        category_name = category.name
        category.delete()
        messages.success(request, f"Category '{category_name}' deleted successfully!")
        return redirect('manager:categories')
    
    context = {'category': category}
    return render(request, 'manager/category_confirm_delete.html', context)


@manager_required
def category_import(request):
    """Bulk import categories from uploaded Excel (.xlsx, .xls) or CSV (.csv) file"""
    if request.method == 'POST':
        uploaded_file = request.FILES.get('excel_file')
        if not uploaded_file:
            messages.error(request, "Please select an Excel (.xlsx) or CSV file to upload.")
            return render(request, 'manager/category_import.html')

        filename = uploaded_file.name.lower()
        created_count = 0
        already_exists_count = 0
        skipped_count = 0

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
                    return render(request, 'manager/category_import.html')
            else:
                messages.error(request, "Unsupported file format. Please upload an Excel (.xlsx) or CSV (.csv) file.")
                return render(request, 'manager/category_import.html')

            if not rows or len(rows) < 2:
                messages.error(request, "The uploaded file is empty or missing data rows (minimum 1 header + 1 data row required).")
                return render(request, 'manager/category_import.html')

            headers = [str(h).strip().lower() for h in rows[0]]
            name_idx = -1
            desc_idx = -1
            active_idx = -1

            for idx, h in enumerate(headers):
                if 'name' in h or 'category' in h or 'title' in h:
                    name_idx = idx
                elif 'desc' in h or 'detail' in h or 'info' in h:
                    desc_idx = idx
                elif 'active' in h or 'status' in h or 'enable' in h:
                    active_idx = idx

            if name_idx == -1:
                name_idx = 0
            if desc_idx == -1 and len(headers) > 1:
                desc_idx = 1
            if active_idx == -1 and len(headers) > 2:
                active_idx = 2

            for row in rows[1:]:
                if not row or not any(row):
                    continue

                name = str(row[name_idx]).strip() if len(row) > name_idx else ""
                desc = str(row[desc_idx]).strip() if (desc_idx != -1 and len(row) > desc_idx) else ""
                active_val = str(row[active_idx]).strip().lower() if (active_idx != -1 and len(row) > active_idx) else "yes"
                is_active = active_val not in ['no', 'false', '0', 'inactive', 'off']

                if not name:
                    skipped_count += 1
                    continue

                if Category.objects.filter(name__iexact=name).exists():
                    already_exists_count += 1
                    continue

                Category.objects.create(
                    name=name,
                    description=desc,
                    is_active=is_active
                )
                created_count += 1

            if created_count > 0:
                msg = f"Bulk import completed successfully! Created {created_count} new categories."
                if already_exists_count > 0:
                    msg += f" {already_exists_count} existing categories were preserved without being overwritten."
                messages.success(request, msg)
                return redirect('manager:categories')
            elif already_exists_count > 0:
                messages.info(
                    request,
                    f"Import completed: All {already_exists_count} categories in the file already existed in the store and were not overwritten."
                )
                return redirect('manager:categories')
            else:
                messages.warning(request, "No valid category names found in the uploaded file.")

        except Exception as e:
            messages.error(request, f"Error processing file: {str(e)}")

    return render(request, 'manager/category_import.html')


@manager_required
def category_sample_template(request):
    """Generates and downloads a sample file (Excel .xlsx or CSV .csv) for bulk category import"""
    format_type = request.GET.get('format', '').strip().lower()

    sample_rows = [
        ["Category Name", "Description", "Active"],
        ["Laptops", "High performance ultrabooks, gaming and productivity laptops", "Yes"],
        ["Smartphones", "5G flagship Android and iOS smartphones with high-res cameras", "Yes"],
        ["Smartwatches", "Fitness trackers and health monitoring connected watches", "Yes"],
        ["Audio & Headphones", "Noise cancelling over-ear headphones and true wireless earbuds", "Yes"],
        ["Keyboards & Mice", "Mechanical gaming keyboards, optical mice, and desktop peripherals", "Yes"],
        ["Monitors & Displays", "4K Ultra HD, curved OLED, and high refresh rate gaming monitors", "Yes"],
        ["Gaming Consoles", "Next-gen gaming consoles, handheld devices, and controllers", "Yes"],
        ["Computer Accessories", "USB-C docks, fast chargers, cables, cooling pads, and sleeves", "Yes"],
    ]

    if format_type == 'csv':
        output = io.StringIO()
        writer = csv.writer(output)
        for row in sample_rows:
            writer.writerow(row)
        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="easytech_categories_template.csv"'
        return response

    try:
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Categories"

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

        ws.column_dimensions['A'].width = 25
        ws.column_dimensions['B'].width = 65
        ws.column_dimensions['C'].width = 15

        output = io.BytesIO()
        wb.save(output)
        output.seek(0)

        response = HttpResponse(
            output.read(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="easytech_categories_template.xlsx"'
        return response

    except (ImportError, Exception):
        output = io.StringIO()
        writer = csv.writer(output)
        for row in sample_rows:
            writer.writerow(row)
        response = HttpResponse(output.getvalue(), content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="easytech_categories_template.csv"'
        return response
