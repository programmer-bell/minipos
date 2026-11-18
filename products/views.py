from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from . import services
from .forms import CategoryForm, ProductForm
from .models import Product


def product_list(request):
    query = request.GET.get("q", "").strip()
    show_inactive = request.GET.get("show_inactive") == "1"

    products = Product.objects.select_related("category")
    if not show_inactive:
        products = products.filter(is_active=True)
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))

    page_obj = Paginator(products, 20).get_page(request.GET.get("page"))

    filters = request.GET.copy()
    filters.pop("page", None)
    return render(
        request,
        "products/product_list.html",
        {
            "page_obj": page_obj,
            "query": query,
            "show_inactive": show_inactive,
            "querystring": filters.urlencode(),
        },
    )


def product_create(request):
    if request.method == "POST":
        form = ProductForm(request.POST)
        if form.is_valid():
            product = services.create_product(
                name=form.cleaned_data["name"],
                sku=form.cleaned_data["sku"],
                category=form.cleaned_data["category"],
                barcode=form.cleaned_data["barcode"],
                price=form.cleaned_data["price"],
                stock_quantity=form.cleaned_data["stock_quantity"],
                created_by=request.user,
            )
            messages.success(request, f'Product "{product.name}" was created.')
            return redirect("products:list")
    else:
        form = ProductForm()
    return render(request, "products/product_form.html", {"form": form})


def product_edit(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        form = ProductForm(request.POST, instance=product)
        if form.is_valid():
            services.update_product(
                product,
                name=form.cleaned_data["name"],
                sku=form.cleaned_data["sku"],
                category=form.cleaned_data["category"],
                barcode=form.cleaned_data["barcode"],
                price=form.cleaned_data["price"],
            )
            messages.success(request, f'Product "{product.name}" was updated.')
            return redirect("products:list")
    else:
        form = ProductForm(instance=product)
    return render(
        request, "products/product_form.html", {"form": form, "product": product}
    )


def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    if request.method == "POST":
        services.deactivate_product(product)
        messages.success(request, f'Product "{product.name}" was deactivated.')
        return redirect("products:list")
    return render(
        request, "products/product_confirm_delete.html", {"product": product}
    )


def category_create(request):
    if request.method == "POST":
        form = CategoryForm(request.POST)
        if form.is_valid():
            category = services.create_category(form.cleaned_data["name"])
            messages.success(request, f'Category "{category.name}" was created.')
            return redirect("products:create")
    else:
        form = CategoryForm()
    return render(request, "products/category_form.html", {"form": form})
