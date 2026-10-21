import json
import re
import django.db.models.deletion
from django.db import migrations, models


def convert_specifications_to_json(apps, schema_editor):
    Product = apps.get_model('products', 'Product')
    products_to_update = []
    delimiters_pattern = re.compile(r'[;\r\n]+')

    for product in Product.objects.all().only('id', 'specifications'):
        raw = product.specifications
        if not raw:
            product.specifications = json.dumps({})
            products_to_update.append(product)
            continue

        if isinstance(raw, dict):
            product.specifications = json.dumps(raw)
            products_to_update.append(product)
            continue

        if not isinstance(raw, str):
            product.specifications = json.dumps({})
            products_to_update.append(product)
            continue

        raw = raw.strip()
        if not raw:
            product.specifications = json.dumps({})
            products_to_update.append(product)
            continue

        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                product.specifications = json.dumps(data)
                products_to_update.append(product)
                continue
        except Exception:
            pass

        parsed = {}
        items = delimiters_pattern.split(raw) if (';' in raw or '\n' in raw) else re.split(r',|[\r\n]+', raw)
        for item in items:
            item = item.strip()
            if not item:
                continue
            if ':' in item:
                k, v = item.split(':', 1)
                if k.strip():
                    parsed[k.strip()] = v.strip()
            else:
                parsed[item] = ''

        product.specifications = json.dumps(parsed)
        products_to_update.append(product)

    if products_to_update:
        Product.objects.bulk_update(products_to_update, ['specifications'], batch_size=500)


def reverse_convert(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('products', '0007_product_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='product',
            name='slug',
            field=models.SlugField(blank=True, max_length=220, unique=True),
        ),
        migrations.RunPython(
            convert_specifications_to_json,
            reverse_code=reverse_convert,
        ),
        migrations.AlterField(
            model_name='product',
            name='specifications',
            field=models.JSONField(blank=True, default=dict, help_text="Structured technical specifications (e.g. {'RAM': '16GB', 'Processor': 'Intel i7'})"),
        ),
        migrations.CreateModel(
            name='ProductImage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(upload_to='products/gallery/')),
                ('alt_text', models.CharField(blank=True, max_length=150)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('product', models.ForeignKey(help_text='Product associated with this gallery image', on_delete=django.db.models.deletion.CASCADE, related_name='gallery_images', to='products.product')),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
