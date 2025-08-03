let cart = JSON.parse(localStorage.getItem('cart')) || [];
let slideIndex = 0;
let selectedCategoryId = null; 
let homeSelectedCategoryId = null; 
let isAddingToCart = false;
let cachedProducts = null;
let cachedCategories = null;
let cachedPromotions = null;
let cachedMainBanner = null;
let currentStep = 1;
let deliveryAddress = '';
let deliveryType = '';
let deliveryMethod = '';
let touchStartX = 0;
let touchCurrentX = 0;
let isSwiping = false;


function setupBackButton() {
    Telegram.WebApp.BackButton.show();
    Telegram.WebApp.BackButton.onClick(() => {
        const isProductPage = !!document.getElementById('product-image');
        const isMainPage = window.location.pathname === '/index.html' || window.location.pathname === '/';
        
        if (isProductPage) {
            window.location.href = '/catalog.html'; 
        } else if (!isMainPage && window.returnToMain) {
            window.location.href = '/index.html';
            window.returnToMain = false; 
        } else {
            Telegram.WebApp.close(); 
        }
    });
}

function startCheckout() {
    if (cart.length === 0) {
        Telegram.WebApp.showAlert("Корзина пуста!");
        return;
    }
    currentStep = 1;
    deliveryAddress = '';
    deliveryType = '';
    deliveryMethod = '';
    document.getElementById('checkout-modal').style.display = 'flex';
    showStep(1);
}

function showStep(step) {
    document.querySelectorAll('.checkout-step').forEach(stepDiv => stepDiv.style.display = 'none');
    document.getElementById(`step-${step}`).style.display = 'block';
    
    if (step <= 3) {
        document.getElementById('modal-title').textContent = `Оформление заказа (Шаг ${step}/3)`;
    }
}

function nextStep(step) {
    if (step === 1) {
        deliveryAddress = document.getElementById('delivery-address').value.trim();
        if (!deliveryAddress) {
            const addressInput = document.getElementById('delivery-address');
            addressInput.classList.add('error-shake');
            addressInput.style.borderColor = '#ff0000';
            setTimeout(() => {
                addressInput.classList.remove('error-shake');
                addressInput.style.borderColor = '#e0e0e0';
            }, 1000);
            return;
        }
        currentStep = 2;
        showStep(2);
        updateDeliveryOptions();
    } else if (step === 2) {
        if (!deliveryType) {
            const options = document.querySelectorAll('.delivery-option');
            options.forEach(option => {
                option.classList.add('error-shake');
                option.querySelector('label').style.color = '#ff0000';
                setTimeout(() => {
                    option.classList.remove('error-shake');
                    option.querySelector('label').style.color = '#333';
                }, 1000);
            });
            return;
        }
        checkStep2Ready(); 
        if (!deliveryMethod) {
            
            const subOptions = document.querySelector(deliveryType === 'pickup' ? '#pickup-options' : '#delivery-options');
            subOptions.classList.add('error-shake');
            subOptions.querySelectorAll('label').forEach(label => {
                label.style.color = '#ff0000';
            });
            setTimeout(() => {
                subOptions.classList.remove('error-shake');
                subOptions.querySelectorAll('label').forEach(label => {
                    label.style.color = '#666';
                });
            }, 1000);
            return;
        }
        currentStep = 3;
        showStep(3);
    }
}

function triggerButtonAnimation() {
    const button = document.getElementById('step-2-next');
    button.classList.add('button-active');
    setTimeout(() => {
        button.classList.remove('button-active');
    }, 100); 
}

function updateDeliveryOptions() {
    const addressLower = deliveryAddress.toLowerCase().trim();
    
   
    const isSpb = /(санкт[-\s]?п[ие]т[еи]р|спб|п[ие]т[еи]р[б]?[у]?[р]?[г]?)/i.test(addressLower);
    
    
    document.getElementById('store-pickup-option').style.display = isSpb ? 'block' : 'none';
    
  
    document.getElementById('yandex-option').style.display = isSpb ? 'block' : 'none';
    document.getElementById('store-delivery-option').style.display = isSpb ? 'block' : 'none';
    
    
    document.querySelectorAll('input[name="pickup-method"], input[name="delivery-method"]').forEach(input => {
        input.checked = false;
    });
    document.getElementById('step-2-next').disabled = true;
}

function showPickupOptions() {
    deliveryType = 'pickup';
    document.getElementById('pickup-options').style.display = 'block';
    document.getElementById('delivery-options').style.display = 'none';
    document.querySelectorAll('input[name="delivery-method"]').forEach(input => input.checked = false);
    checkStep2Ready();
}

function showDeliveryOptions() {
    deliveryType = 'delivery';
    document.getElementById('pickup-options').style.display = 'none';
    document.getElementById('delivery-options').style.display = 'block';
    document.querySelectorAll('input[name="pickup-method"]').forEach(input => input.checked = false);
    checkStep2Ready();
}

function checkStep2Ready() {
    const pickupRadios = document.querySelectorAll('input[name="pickup-method"]');
    const deliveryRadios = document.querySelectorAll('input[name="delivery-method"]');
    deliveryMethod = '';
    
    if (deliveryType === 'pickup') {
        pickupRadios.forEach(radio => {
            if (radio.checked) deliveryMethod = radio.value;
        });
    } else if (deliveryType === 'delivery') {
        deliveryRadios.forEach(radio => {
            if (radio.checked) deliveryMethod = radio.value;
        });
    }
    
    document.getElementById('step-2-next').disabled = !deliveryMethod;
}
async function finishOrder() {
    const name = document.getElementById('customer-name').value.trim();
    const phone = document.getElementById('customer-phone').value.trim();
    const submitButton = document.querySelector('#step-3 button[onclick="finishOrder()"]');

    if (!name || !phone) {
        Telegram.WebApp.showAlert('Ошибка: заполните имя и телефон');
        return;
    }

    if (submitButton.disabled) return;
    submitButton.disabled = true;
    submitButton.textContent = 'Отправка...';

    const orderData = {
        action: 'checkout',
        customer: { name, phone },
        cart: cart,
        delivery: {
            address: deliveryAddress,
            type: deliveryType,
            method: deliveryMethod
        },
        total: cart.reduce((sum, item) => sum + item.price * item.quantity, 0),
        username: Telegram.WebApp.initDataUnsafe.user?.username || 'Unknown',
        user_id: Telegram.WebApp.initDataUnsafe.user?.id || null
    };

    console.log('Sending order data:', orderData);

    try {
        const checkoutResponse = await fetch('/api/checkout', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData)
        });

        const checkoutResult = await checkoutResponse.json();
        if (!checkoutResponse.ok) {
            throw new Error(checkoutResult.message || 'Ошибка сервера');
        }

        console.log('Order saved with ID:', checkoutResult.order_id);
        console.log('Payment URL:', checkoutResult.payment_url);

        localStorage.setItem('pendingOrderId', checkoutResult.order_id);

        window.location.href = checkoutResult.payment_url;

    } catch (error) {
        console.error('Error submitting order:', error);
        Telegram.WebApp.showAlert(`Ошибка при отправке заказа: ${error.message}`);
        submitButton.disabled = false;
        submitButton.textContent = 'Закончить оформление заказа';
    }
}

function closeModal() {
    document.getElementById('checkout-modal').style.display = 'none';
}

function isCacheValid(key, serverLastUpdated, ttl = 48 * 60 * 60 * 1000) {
    const cacheTime = localStorage.getItem(`${key}_timestamp`);
    const cachedLastUpdated = localStorage.getItem(`${key}_last_updated`);
    if (!cacheTime || !cachedLastUpdated) return false;
    const now = Date.now();
    const isFresh = (now - parseInt(cacheTime, 10)) < ttl;
    const isUpToDate = serverLastUpdated === cachedLastUpdated;
    return isFresh && isUpToDate;
}

function showLoader() {
    const loader = document.querySelector('.loader');
    if (loader) loader.classList.add('active');
}

function hideLoader() {
    const loader = document.querySelector('.loader');
    if (loader) loader.classList.remove('active');
}

function updateNavLine() {
    requestAnimationFrame(() => {
        const activeBtn = document.querySelector('.nav-btn.active');
        const navLine = document.querySelector('.nav-line');
        if (activeBtn && navLine) {
            const btnRect = activeBtn.getBoundingClientRect();
            const navRect = document.querySelector('.bottom-nav').getBoundingClientRect();
            const targetLeft = btnRect.left - navRect.left + (btnRect.width * 0.3); 
            const targetWidth = btnRect.width * 0.4;

            const lastLeft = parseFloat(localStorage.getItem('navLineLeft')) || targetLeft;
            const lastWidth = parseFloat(localStorage.getItem('navLineWidth')) || targetWidth;

            navLine.style.left = `${lastLeft}px`;
            navLine.style.width = `${lastWidth}px`;
            navLine.style.transition = 'none';

            requestAnimationFrame(() => {
                navLine.style.transition = 'all 0.6s cubic-bezier(0.4, 0, 0.2, 1)';
                navLine.style.left = `${targetLeft}px`;
                navLine.style.width = `${targetWidth}px`;

                navLine.classList.add('stretch-animate');

                navLine.addEventListener('transitionend', () => {
                    navLine.classList.remove('stretch-animate');
                    navLine.style.transition = '';
                    localStorage.setItem('navLineLeft', targetLeft);
                    localStorage.setItem('navLineWidth', targetWidth);
                }, { once: true });
            });
        }
    });
}

async function preloadData() {
    if (cachedCategories && cachedProducts && cachedPromotions && cachedMainBanner) {
        console.log('Using cached data from memory');
        return;
    }

    showLoader();
    try {
        const [catResponse, prodResponse, promoResponse, bannerResponse] = await Promise.all([
            fetch('/api/categories').then(res => res.ok ? res.json() : Promise.reject('Categories fetch failed')),
            fetch('/api/products').then(res => res.ok ? res.json() : Promise.reject('Products fetch failed')),
            fetch('/api/promotions').then(res => res.ok ? res.json() : Promise.reject('Promotions fetch failed')),
            fetch('/api/main_banner').then(res => res.ok ? res.json() : Promise.reject('Main banner fetch failed'))
        ]);

        const now = Date.now();
        
        cachedCategories = catResponse;
        localStorage.setItem('categories', JSON.stringify(cachedCategories));
        localStorage.setItem('categories_timestamp', now);

        cachedProducts = prodResponse;
        localStorage.setItem('products', JSON.stringify(cachedProducts));
        localStorage.setItem('products_timestamp', now);

        // Акции
        cachedPromotions = promoResponse.promotions;
        const promoLastUpdated = promoResponse.last_updated;
        if (!isCacheValid('promotions', promoLastUpdated) || !localStorage.getItem('promotions')) {
            localStorage.setItem('promotions', JSON.stringify(cachedPromotions));
            localStorage.setItem('promotions_timestamp', now);
            localStorage.setItem('promotions_last_updated', promoLastUpdated);
        }

        cachedMainBanner = bannerResponse;
        const bannerLastUpdated = bannerResponse.last_updated;
        if (!isCacheValid('main_banner', bannerLastUpdated) || !localStorage.getItem('main_banner')) {
            localStorage.setItem('main_banner', JSON.stringify(cachedMainBanner));
            localStorage.setItem('main_banner_timestamp', now);
            localStorage.setItem('main_banner_last_updated', bannerLastUpdated);
        }

        console.log('Data fetched and cached successfully');
    } catch (error) {
        console.error('Error preloading data:', error);
        cachedCategories = cachedCategories || JSON.parse(localStorage.getItem('categories')) || [];
        cachedProducts = cachedProducts || JSON.parse(localStorage.getItem('products')) || [];
        cachedPromotions = cachedPromotions || JSON.parse(localStorage.getItem('promotions')) || [];
        cachedMainBanner = cachedMainBanner || JSON.parse(localStorage.getItem('main_banner')) || {};
    } finally {
        hideLoader();
    }
}

async function loadCategories() {
    await preloadData();
    const categoryBanners = document.querySelector('.category-banners');
    if (!categoryBanners) return;
    categoryBanners.innerHTML = '';
    if (!cachedCategories || cachedCategories.length === 0) {
        categoryBanners.innerHTML = '<p>Категории отсутствуют</p>';
        console.log('No categories available');
        return;
    }
    cachedCategories.forEach(category => {
        const banner = document.createElement('div');
        banner.className = 'category-banner';
        banner.dataset.categoryId = category.id;
        banner.style.backgroundImage = category.image ? `url('data:image/jpeg;base64,${category.image}')` : 'url(https://via.placeholder.com/150x150?text=Нет+фото)';
        banner.addEventListener('click', () => toggleCategoryFilter(category.id));
        categoryBanners.appendChild(banner);
    });
}

function toggleCategoryFilter(categoryId) {
    const banners = document.querySelectorAll('.category-banner');
    if (selectedCategoryId === categoryId) {
        selectedCategoryId = null;
        banners.forEach(b => b.classList.remove('active'));
    } else {
        selectedCategoryId = categoryId;
        banners.forEach(b => {
            b.classList.toggle('active', b.dataset.categoryId == categoryId);
        });
    }
    loadProducts();
}

function toggleSearch() {
    const searchBar = document.getElementById('search-bar');
    searchBar.classList.toggle('active');
    if (!searchBar.classList.contains('active')) {
        document.getElementById('search-input').value = '';
        loadProducts();
    }
}

function searchProducts() {
    const query = document.getElementById('search-input').value.toLowerCase();
    loadProducts(query);
}

async function loadProducts(searchQuery = '') {
    await preloadData();
    let products = cachedProducts || [];
    if (selectedCategoryId) {
        products = products.filter(product => product.category_id === selectedCategoryId);
    }
    if (searchQuery) {
        products = products.filter(product => product.name.toLowerCase().includes(searchQuery));
    }
    const catalogGrid = document.querySelector('.catalog-grid');
    if (!catalogGrid) return;
    catalogGrid.innerHTML = '';
    if (products.length === 0) {
        catalogGrid.innerHTML = '<p>Товары отсутствуют</p>';
        console.log('No products available');
        return;
    }
    products.forEach(product => {
        const imageSrc = product.image ? `data:image/jpeg;base64,${product.image}` : 'https://via.placeholder.com/300x200?text=Нет+фото';
        catalogGrid.innerHTML += `
            <div class="product-card" onclick="showProductDetails(${product.id})">
                <div class="product-image" style="background-image: url('${imageSrc}')"></div>
                <div class="product-details">
                    <p class="product-price">${product.price} ₽</p>
                    <h3 class="product-name">${product.name}</h3>
                    <button class="product-button" onclick="event.stopPropagation(); showProductDetails(${product.id})">Подробнее</button>
                </div>
            </div>
        `;
    });
}

function showProductDetails(id) {
    window.location.href = `/product.html?id=${id}`;
}

async function loadProductDetails(id) {
    const numericId = Number(id);
    await preloadData();
    const response = await fetch(`/api/products/${numericId}`);
    const product = await response.json();

    if (!response.ok) {
        Telegram.WebApp.showAlert('Товар не найден');
        return;
    }

    const imageContainer = document.getElementById('product-image');
    imageContainer.innerHTML = '';
    const slider = document.createElement('div');
    slider.className = 'image-slider';
    let currentColorImages = product.main_images && product.main_images.length > 0 ? product.main_images : [];
    if (currentColorImages.length === 0) {
        const noImage = document.createElement('div');
        noImage.className = 'slider-image';
        noImage.style.backgroundImage = 'url(https://via.placeholder.com/300x200?text=Нет+фото)';
        slider.appendChild(noImage);
    } else {
        currentColorImages.forEach((image) => {
            const img = document.createElement('div');
            img.className = 'slider-image';
            img.style.backgroundImage = `url('data:image/jpeg;base64,${image}')`;
            slider.appendChild(img);
        });
    }
    imageContainer.appendChild(slider);

    document.getElementById('product-name').textContent = product.name;
    document.getElementById('product-price').textContent = `${product.price} ₽`;
    document.getElementById('product-description').textContent = product.description || 'Описание отсутствует';

    const colorsElement = document.getElementById('product-colors');
    colorsElement.innerHTML = '';
    const colorMap = {
        'Белый': '#FFFFFF',
        'Чёрный': '#000000',
        'Красный': '#FF0000',
        'Бежевый': '#F5F5DC',
        'Серый': '#808080',
        'Оранжевый': '#FFA500',
        'Синий': '#0000FF',
        'Фиолетовый': '#800080',
        'Зелёный': '#008000',
        'Голубой': '#00FFFF'
    };
    product.colors.forEach((colorObj) => {
        const colorButton = document.createElement('button');
        colorButton.className = 'color-button';
        colorButton.style.backgroundColor = colorMap[colorObj.color] || '#CCCCCC';
        colorButton.dataset.color = colorObj.color;
        colorButton.addEventListener('click', () => {
            document.querySelectorAll('.color-button').forEach(btn => btn.classList.remove('active'));
            colorButton.classList.add('active');
            currentColorImages = colorObj.images.length > 0 ? colorObj.images : product.main_images || [];
            slider.innerHTML = '';
            if (currentColorImages.length === 0) {
                const noImage = document.createElement('div');
                noImage.className = 'slider-image';
                noImage.style.backgroundImage = 'url(https://via.placeholder.com/300x200?text=Нет+фото)';
                slider.appendChild(noImage);
            } else {
                currentColorImages.forEach((image) => {
                    const img = document.createElement('div');
                    img.className = 'slider-image';
                    img.style.backgroundImage = `url('data:image/jpeg;base64,${image}')`;
                    slider.appendChild(img);
                });
            }
            const button = document.querySelector('.add-to-cart-button');
            const selectedSize = button.dataset.selectedSize;
            if (selectedSize) {
                updateCartButton(button, numericId, selectedSize, colorObj.color);
            }
        });
        colorsElement.appendChild(colorButton);
    });

    const sizesElement = document.getElementById('product-sizes');
    sizesElement.innerHTML = '';
    const sizes = product.sizes ? product.sizes.split(',') : [];
    sizes.forEach(size => {
        const sizeButton = document.createElement('button');
        sizeButton.className = 'size-button';
        sizeButton.textContent = size;
        sizeButton.dataset.size = size;
        sizeButton.addEventListener('click', () => {
            document.querySelectorAll('.size-button').forEach(btn => btn.classList.remove('active'));
            sizeButton.classList.add('active');
            const button = document.querySelector('.add-to-cart-button');
            button.dataset.selectedSize = size;
            const selectedColor = document.querySelector('.color-button.active')?.dataset.color || product.colors[0]?.color;
            updateCartButton(button, numericId, size, selectedColor);
        });
        sizesElement.appendChild(sizeButton);
    });

    const button = document.querySelector('.add-to-cart-button');
    button.dataset.productId = numericId;

    const cartItem = cart.find(item => item.id === numericId);
    let defaultSize = cartItem ? cartItem.size.trim() : '';
    let defaultColor = cartItem ? cartItem.color : product.colors[0]?.color || '';

    if (cartItem && defaultSize) {
        const sizeButton = document.querySelector(`.size-button[data-size="${defaultSize}"]`);
        if (sizeButton) {
            sizeButton.classList.add('active');
            button.dataset.selectedSize = defaultSize;
        }
    }

    if (defaultColor) {
        const colorButton = document.querySelector(`.color-button[data-color="${defaultColor}"]`);
        if (colorButton) {
            colorButton.classList.add('active');
            const colorObj = product.colors.find(c => c.color === defaultColor);
            currentColorImages = colorObj && colorObj.images.length > 0 ? colorObj.images : product.main_images || [];
            slider.innerHTML = '';
            if (currentColorImages.length === 0) {
                const noImage = document.createElement('div');
                noImage.className = 'slider-image';
                noImage.style.backgroundImage = 'url(https://via.placeholder.com/300x200?text=Нет+фото)';
                slider.appendChild(noImage);
            } else {
                currentColorImages.forEach((image) => {
                    const img = document.createElement('div');
                    img.className = 'slider-image';
                    img.style.backgroundImage = `url('data:image/jpeg;base64,${image}')`;
                    slider.appendChild(img);
                });
            }
        }
    }

    if (cartItem && defaultSize && defaultColor) {
        const matchingCartItem = cart.find(item => 
            item.id === numericId && 
            item.size.trim() === defaultSize.trim() && 
            item.color === defaultColor
        );
        if (matchingCartItem) {
            updateCartButton(button, numericId, defaultSize, defaultColor);
            button.onclick = null;
        } else {
            button.textContent = 'Добавить в корзину';
            button.style.backgroundColor = '#e0e0e0';
            button.style.color = '#333';
            button.removeEventListener('click', addToCart);
            button.addEventListener('click', addToCart);
        }
    } else {
        button.textContent = 'Добавить в корзину';
        button.style.backgroundColor = '#e0e0e0';
        button.style.color = '#333';
        button.removeEventListener('click', addToCart);
        button.addEventListener('click', addToCart);
    }

    let similarProducts = cachedProducts.filter(p => p.category_id === product.category_id && p.id !== product.id);
    const similarProductsContainer = document.getElementById('similar-products');
    similarProductsContainer.innerHTML = '';
    similarProducts.forEach(similarProduct => {
        const imageSrc = similarProduct.image ? `data:image/jpeg;base64,${similarProduct.image}` : 'https://via.placeholder.com/300x200?text=Нет+фото';
        similarProductsContainer.innerHTML += `
            <div class="product-card" onclick="showProductDetails(${similarProduct.id})">
                <div class="product-image" style="background-image: url('${imageSrc}')"></div>
                <div class="product-details">
                    <p class="product-price">${similarProduct.price} ₽</p>
                    <h3 class="product-name">${similarProduct.name}</h3>
                    <button class="product-button" onclick="event.stopPropagation(); showProductDetails(${similarProduct.id})">Подробнее</button>
                </div>
            </div>
        `;
    });
}

function toggleDescription() {
    const descriptionContainer = document.getElementById('product-description-container');
    const arrow = document.querySelector('.arrow-icon');
    if (descriptionContainer.style.maxHeight === '0px' || !descriptionContainer.style.maxHeight) {
        descriptionContainer.style.maxHeight = descriptionContainer.scrollHeight + 'px';
        arrow.classList.add('up');
    } else {
        descriptionContainer.style.maxHeight = '0px';
        arrow.classList.remove('up');
    }
}

function addToCart() {
    if (isAddingToCart) return;
    isAddingToCart = true;

    const button = document.querySelector('.add-to-cart-button');
    const productId = parseInt(button.dataset.productId);
    const selectedSize = button.dataset.selectedSize;

    if (!selectedSize) {
        const sizeButtons = document.querySelectorAll('.size-button');
        sizeButtons.forEach(btn => {
            btn.classList.add('error-shake');
            setTimeout(() => btn.classList.remove('error-shake'), 1000);
        });
        isAddingToCart = false;
        return;
    }

    fetch(`/api/products/${productId}`).then(response => response.json()).then(product => {
        const selectedColor = document.querySelector('.color-button.active')?.dataset.color || product.colors[0]?.color;
        
        const item = cart.find(i => i.id === productId && i.size === selectedSize && i.color === selectedColor);
        if (item) {
            item.quantity += 1;
        } else {
            cart.push({ id: productId, name: product.name, price: product.price, size: selectedSize, color: selectedColor, quantity: 1 });
        }
        localStorage.setItem('cart', JSON.stringify(cart));
        updateCartButton(button, productId, selectedSize, selectedColor);
        displayCart();
        isAddingToCart = false;
    }).catch(error => {
        console.error('Error in addToCart:', error);
        isAddingToCart = false;
    });
}

function updateCartButton(button, productId, size, color) {
    const numericProductId = Number(productId);
    const trimmedSize = size.trim();
    const item = cart.find(i => 
        i.id === numericProductId && 
        i.size.trim() === trimmedSize && 
        i.color === color
    );

    if (!item) return;

    if (!button.style.width) {
        button.style.width = button.offsetWidth + 'px';
    }

    button.style.backgroundColor = '#e0e0e0';
    button.style.color = '#333';
    button.innerHTML = `
        <span style="font-size: 16px;">В корзине</span>
        <div style="display: flex; align-items: center; gap: 5px;">
            <button onclick="changeCartQuantity(${numericProductId}, '${trimmedSize}', '${color}', -1); event.stopPropagation();" style="background: none; border: none; font-size: 16px; padding: 0 5px; cursor: pointer; line-height: 1; color: #333;">-</button>
            <span style="font-size: 16px; min-width: 20px; text-align: center;">${item.quantity}</span>
            <button onclick="changeCartQuantity(${numericProductId}, '${trimmedSize}', '${color}', 1); event.stopPropagation();" style="background: none; border: none; font-size: 16px; padding: 0 5px; cursor: pointer; line-height: 1; color: #333;">+</button>
        </div>
    `;
    button.style.display = 'flex';
    button.style.justifyContent = 'space-between';
    button.style.alignItems = 'center';
    button.style.padding = '12px 15px';
    button.style.boxSizing = 'border-box';
    button.onclick = null;
}

function changeCartQuantity(productId, size, color, delta) {
    const item = cart.find(i => i.id === productId && i.size === size && i.color === color);
    if (!item) return;

    item.quantity += delta;
    if (item.quantity <= 0) {
        cart = cart.filter(i => i !== item);
        const button = document.querySelector('.add-to-cart-button');
        button.style.backgroundColor = '#e0e0e0';
        button.style.color = '#333';
        button.innerHTML = 'Добавить в корзину';
        button.removeEventListener('click', addToCart);
        button.addEventListener('click', addToCart);
    } else {
        updateCartButton(document.querySelector('.add-to-cart-button'), productId, size, color);
    }
    localStorage.setItem('cart', JSON.stringify(cart));
    displayCart();
}

async function loadMainBanner() {
    await preloadData();
    const bannerContainer = document.getElementById('main-banner');
    if (!bannerContainer) return;
    if (cachedMainBanner && cachedMainBanner.image) {
        bannerContainer.innerHTML = `
            <img src="data:image/jpeg;base64,${cachedMainBanner.image}" alt="Главный баннер">
        `;
        console.log('Main banner loaded');
    } else {
        bannerContainer.innerHTML = `
            <img src="https://via.placeholder.com/500x200?text=Главный+баннер+не+задан" alt="Главный баннер">
        `;
        console.log('No main banner available');
    }
}

async function loadPromotions() {
    await preloadData();
    const promoList = document.getElementById('promo-list');
    if (!promoList) return;
    promoList.innerHTML = '';
    if (!cachedPromotions || cachedPromotions.length === 0) {
        promoList.innerHTML = '<p>Акции отсутствуют</p>';
        console.log('No promotions available');
        return;
    }
    cachedPromotions.forEach(promo => {
        const imageSrc = promo.banner_image ? `data:image/jpeg;base64,${promo.banner_image}` : 'https://via.placeholder.com/200x200?text=Нет+фото';
        promoList.innerHTML += `
            <div class="promotion">
                <img src="${imageSrc}" alt="Акция">
            </div>
        `;
    });
}

async function loadHomeCategories() {
    await preloadData();
    const categoryBanners = document.querySelector('#home-category-banners');
    if (!categoryBanners) return;
    categoryBanners.innerHTML = '';
    if (!cachedCategories || cachedCategories.length === 0) {
        categoryBanners.innerHTML = '<p>Категории отсутствуют</p>';
        console.log('No home categories available');
        return;
    }
    cachedCategories.forEach(category => {
        const banner = document.createElement('div');
        banner.className = 'category-banner';
        banner.dataset.categoryId = category.id;
        banner.style.backgroundImage = category.image ? `url('data:image/jpeg;base64,${category.image}')` : 'url(https://via.placeholder.com/150x150?text=Нет+фото)';
        banner.addEventListener('click', () => toggleHomeCategoryFilter(category.id));
        categoryBanners.appendChild(banner);
    });
}

function toggleHomeCategoryFilter(categoryId) {
    const banners = document.querySelectorAll('#home-category-banners .category-banner');
    if (homeSelectedCategoryId === categoryId) {
        homeSelectedCategoryId = null;
        banners.forEach(b => b.classList.remove('active'));
    } else {
        homeSelectedCategoryId = categoryId;
        banners.forEach(b => {
            b.classList.toggle('active', b.dataset.categoryId == categoryId);
        });
    }
    loadHomeProducts();
}

async function loadHomeProducts() {
    await preloadData();
    let products = cachedProducts || [];
    if (homeSelectedCategoryId) {
        products = products.filter(product => product.category_id === homeSelectedCategoryId);
    }
    const catalogGrid = document.querySelector('#home-catalog-grid');
    if (!catalogGrid) return;
    catalogGrid.innerHTML = '';
    if (products.length === 0) {
        catalogGrid.innerHTML = '<p>Товары отсутствуют</p>';
        console.log('No home products available');
        return;
    }
    products.forEach(product => {
        const imageSrc = product.image ? `data:image/jpeg;base64,${product.image}` : 'https://via.placeholder.com/300x200?text=Нет+фото';
        catalogGrid.innerHTML += `
            <div class="product-card" onclick="showProductDetails(${product.id})">
                <div class="product-image" style="background-image: url('${imageSrc}')"></div>
                <div class="product-details">
                    <p class="product-price">${product.price} ₽</p>
                    <h3 class="product-name">${product.name}</h3>
                    <button class="product-button" onclick="event.stopPropagation(); showProductDetails(${product.id})">Подробнее</button>
                </div>
            </div>
        `;
    });
}

async function displayCart() {
    await preloadData();
    const cartItems = document.getElementById('cart-items');
    const cartFooter = document.querySelector('.cart-footer');
    const totalElement = document.getElementById('total');
    let total = 0;

    if (!cartItems) return;

    if (cart.length === 0) {
        cartItems.innerHTML = '<p class="empty-cart">Ваша корзина пуста</p>';
        cartFooter.style.display = 'none';
        return;
    }

    cartFooter.style.display = 'flex';

    const cartItemIds = new Set(cart.map(item => `${item.id}-${item.size}-${item.color}`));
    Array.from(cartItems.children).forEach(element => {
        const itemId = element.dataset.itemId;
        if (!cartItemIds.has(itemId)) {
            element.remove();
        }
    });

    cart.forEach((item, index) => {
        const itemId = `${item.id}-${item.size}-${item.color}`;
        let existingItem = cartItems.querySelector(`[data-item-id="${itemId}"]`);
        const product = cachedProducts.find(p => p.id === item.id);
        const imageSrc = product && product.image ? `data:image/jpeg;base64,${product.image}` : 'https://via.placeholder.com/80x80?text=Нет+фото';
        const itemTotal = item.price * item.quantity;
        total += itemTotal;

        if (existingItem) {
            existingItem.querySelector('.cart-item-quantity span').textContent = item.quantity;
            existingItem.querySelector('.cart-item-price').textContent = `${item.price} ₽`;
        } else {
            const newItem = document.createElement('div');
            newItem.className = 'cart-item';
            newItem.dataset.itemId = itemId;
            newItem.innerHTML = `
                <div class="cart-item-image" style="background-image: url('${imageSrc}')"></div>
                <div class="cart-item-details">
                    <h3 class="cart-item-name">${item.name}</h3>
                    <p class="cart-item-options">Размер: ${item.size}, Цвет: ${item.color}</p>
                </div>
                <p class="cart-item-price">${item.price} ₽</p>
                <div class="cart-item-quantity">
                    <button onclick="changeQuantity(${index}, -1)">-</button>
                    <span>${item.quantity}</span>
                    <button onclick="changeQuantity(${index}, 1)">+</button>
                </div>
            `;
            cartItems.appendChild(newItem);
        }
    });

    const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);

    let itemsWithDiscount = [];
    cart.forEach(item => {
        for (let i = 0; i < item.quantity; i++) {
            itemsWithDiscount.push({ price: item.price });
        }
    });

    itemsWithDiscount.sort((a, b) => a.price - b.price);

    let totalWithDiscount = 0;
    let discount = 0;

    itemsWithDiscount.forEach((item, index) => {
        let itemPrice = item.price;
        if (index === 1 && totalItems >= 2) { 
            itemPrice *= 0.9; 
            discount += item.price * 0.1;
        } else if (index === 2 && totalItems >= 3) { 
            itemPrice *= 0.8;
            discount += item.price * 0.2;
        } else {
            itemPrice = item.price; 
        }
        totalWithDiscount += itemPrice;
    });

    totalElement.innerHTML = `
        ${discount > 0 ? `<span class="original-price">${total.toFixed(2)} ₽</span><br>` : ''}
        <span class="total-label">Итого: </span><span class="total-amount">${totalWithDiscount.toFixed(2)} ₽</span>
    `;
}

function changeQuantity(index, delta) {
    cart[index].quantity += delta;
    if (cart[index].quantity <= 0) {
        cart.splice(index, 1);
    }
    localStorage.setItem('cart', JSON.stringify(cart));
    displayCart(); 
}

function handleSwipe() {
    const productDetail = document.querySelector('.container');
    const threshold = 100;

    productDetail.addEventListener('touchstart', (e) => {
        touchStartX = e.touches[0].clientX;
        isSwiping = true;
        productDetail.style.transition = 'none';
    });

    productDetail.addEventListener('touchmove', (e) => {
        if (!isSwiping) return;
        touchCurrentX = e.touches[0].clientX;
        const diffX = touchCurrentX - touchStartX;

        if (touchStartX <= 50 && diffX > 0) {
            productDetail.style.transform = `translateX(${diffX}px)`;
            e.preventDefault();
        }
    });

    productDetail.addEventListener('touchend', () => {
        if (!isSwiping) return;
        isSwiping = false;
        const diffX = touchCurrentX - touchStartX;

        if (diffX > threshold && touchStartX <= 50) {
            productDetail.style.transition = 'transform 0.3s ease-out';
            productDetail.style.transform = `translateX(100%)`;
            setTimeout(() => {
                window.location.href = '/catalog.html';
            }, 300);
        } else {
            productDetail.style.transition = 'transform 0.3s ease-out';
            productDetail.style.transform = `translateX(0)`;
        }
    });
}

document.addEventListener('DOMContentLoaded', () => {
    Telegram.WebApp.ready();
    Telegram.WebApp.expand();

    if (!document.querySelector('.loader')) {
        const loader = document.createElement('div');
        loader.className = 'loader';
        loader.innerHTML = '<div class="loader-spinner"></div>';
        document.body.appendChild(loader);
    }

    preloadData().then(() => {
        const user = Telegram.WebApp.initDataUnsafe.user || {};
        const userNameInnerElement = document.querySelector('.user-name-inner');
        const avatar = document.querySelector('.avatar');

        console.log('Telegram User Data:', user);

        if (userNameInnerElement && avatar) {
            const displayName = user.first_name 
                ? user.first_name 
                : (user.username ? `@${user.username}` : 'Гость');
            userNameInnerElement.textContent = displayName;
            if (user.photo_url) {
                avatar.style.backgroundImage = `url(${user.photo_url})`;
                avatar.textContent = '';
            } else {
                avatar.textContent = user.first_name ? user.first_name[0] : 'Г';
            }
        }

        const pendingOrderId = localStorage.getItem('pendingOrderId');
        if (pendingOrderId) {
            fetch(`/api/check_order_status?order_id=${pendingOrderId}`)
                .then(response => response.json())
                .then(result => {
                    console.log('Order status:', result);
                    if (result.status === 'CONFIRMED') {
                        cart = [];
                        localStorage.setItem('cart', JSON.stringify(cart));
                        localStorage.removeItem('pendingOrderId');
                        displayCart(); 
                    }
                })
                .catch(error => {
                    console.error('Error checking order status:', error);
                });
        }

        if (document.querySelector('.catalog-grid')) {
            loadCategories();
            loadProducts();
        }
        if (document.getElementById('promo-list')) {
            loadPromotions();
        }
        if (document.getElementById('cart-items')) {
            displayCart();
        }
        if (document.getElementById('main-banner')) {
            loadMainBanner();
            loadHomeCategories();
            loadHomeProducts();
        }
        if (document.getElementById('product-image') && !window.productLoaded) {
            const urlParams = new URLSearchParams(window.location.search);
            const productId = urlParams.get('id');
            if (productId) {
                window.productLoaded = true;
                loadProductDetails(productId);
                handleSwipe();
            }
        }

        setupBackButton();
        updateNavLine();

        document.querySelectorAll('.nav-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                updateNavLine();
                window.location.href = btn.getAttribute('href');
            });
        });

        document.querySelectorAll('input[name="pickup-method"], input[name="delivery-method"]').forEach(radio => {
            radio.addEventListener('change', checkStep2Ready);
        });
    }).catch(error => {
        console.error('Error during preloadData:', error);
    });

    window.addEventListener('load', hideLoader);
    window.addEventListener('resize', updateNavLine);
});