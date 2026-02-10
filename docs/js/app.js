/**
 * Print28 Photo Cropper - Mini App
 * Telegram WebApp integration for photo cropping
 */

class PhotoCropperApp {
    constructor() {
        // Telegram WebApp
        this.tg = window.Telegram?.WebApp;
        
        // State
        this.photos = [];
        this.currentIndex = 0;
        this.cropData = {}; // {photoId: {x, y, width, height, rotation, flip}}
        this.cropper = null;
        this.isLoading = false;
        
        // Default aspect ratio (used as fallback)
        this.defaultAspectRatio = 0.76;
        
        // DOM elements
        this.elements = {
            cropImage: document.getElementById('cropImage'),
            cropperWrapper: document.getElementById('cropperWrapper'),
            loading: document.getElementById('loading'),
            errorState: document.getElementById('errorState'),
            
            currentIndex: document.getElementById('currentIndex'),
            totalPhotos: document.getElementById('totalPhotos'),
            formatBadge: document.getElementById('formatBadge'),
            confidenceIndicator: document.getElementById('confidenceIndicator'),
            hint: document.getElementById('hint'),
            
            navDots: document.getElementById('navDots'),
            btnPrev: document.getElementById('btnPrev'),
            btnNext: document.getElementById('btnNext'),
            
            btnReset: document.getElementById('btnReset'),
            btnAutoCrop: document.getElementById('btnAutoCrop'),
            btnRotate: document.getElementById('btnRotate'),
            btnFlip: document.getElementById('btnFlip'),
            btnSave: document.getElementById('btnSave'),
            
            toast: document.getElementById('toast')
        };
        
        this.init();
    }
    
    init() {
        if (this.tg) {
            this.tg.ready();
            this.tg.expand();
            
            document.documentElement.style.setProperty('--bg-primary', 
                this.tg.themeParams.bg_color || '#17212b');
            document.documentElement.style.setProperty('--bg-secondary', 
                this.tg.themeParams.secondary_bg_color || '#0e1621');
            document.documentElement.style.setProperty('--text-primary', 
                this.tg.themeParams.text_color || '#f5f5f5');
            document.documentElement.style.setProperty('--accent', 
                this.tg.themeParams.button_color || '#5eb5f7');
        }
        
        this.bindEvents();
        this.loadPhotosData();
    }
    
    bindEvents() {
        this.elements.btnPrev.addEventListener('click', () => this.navigate(-1));
        this.elements.btnNext.addEventListener('click', () => this.navigate(1));
        
        this.elements.btnReset.addEventListener('click', () => this.resetCrop());
        this.elements.btnAutoCrop.addEventListener('click', () => this.autoCrop());
        this.elements.btnRotate.addEventListener('click', () => this.rotate());
        this.elements.btnFlip.addEventListener('click', () => this.flip());
        
        this.elements.btnSave.addEventListener('click', () => this.saveAll());
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowLeft') this.navigate(-1);
            if (e.key === 'ArrowRight') this.navigate(1);
        });
    }
    
    async loadPhotosData() {
        const urlParams = new URLSearchParams(window.location.search);
        const orderId = urlParams.get('order_id');
        
        if (orderId) {
            try {
                this.showLoading(true);
                const apiBase = urlParams.get('api_url') || 'http://localhost:8080';
                const response = await fetch(`${apiBase}/api/photos/${orderId}`);
                
                if (response.ok) {
                    const data = await response.json();
                    this.photos = data.photos.map(p => ({
                        ...p,
                        url: p.url.startsWith('http') ? p.url : `${apiBase}${p.url}`
                    }));
                    this.orderId = data.order_id;
                    this.orderNumber = data.order_number;
                } else {
                    this.photos = this.getDemoPhotos();
                }
            } catch (e) {
                console.error('Failed to load from API:', e);
                this.photos = this.getDemoPhotos();
            }
        } else {
            if (this.tg?.initDataUnsafe?.start_param) {
                try {
                    const data = JSON.parse(atob(this.tg.initDataUnsafe.start_param));
                    this.photos = data.photos || [];
                } catch (e) {
                    console.error('Failed to parse start_param:', e);
                }
            }
            
            if (this.photos.length === 0) {
                this.photos = this.getDemoPhotos();
            }
        }
        
        this.elements.totalPhotos.textContent = this.photos.length;
        this.renderNavDots();
        this.loadPhoto(0);
    }
    
    getDemoPhotos() {
        return [
            {
                id: 1,
                url: 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800',
                product_name: 'Полароид верт.',
                aspect_ratio: 0.76,
                auto_crop: { x: 0, y: 0, width: 800, height: 1052 },
                confidence: 0.92
            },
            {
                id: 2,
                url: 'https://images.unsplash.com/photo-1469474968028-56623f02e42e?w=800',
                product_name: 'Полароид верт.',
                aspect_ratio: 0.76,
                auto_crop: { x: 100, y: 50, width: 600, height: 789 },
                confidence: 0.78
            },
            {
                id: 3,
                url: 'https://images.unsplash.com/photo-1501854140801-50d01698950b?w=800',
                product_name: 'Классика б/рамки',
                aspect_ratio: 0.667,
                auto_crop: { x: 0, y: 100, width: 800, height: 1200 },
                confidence: 0.45
            }
        ];
    }
    
    renderNavDots() {
        this.elements.navDots.innerHTML = '';
        if (this.photos.length <= 10) {
            this.photos.forEach((_, index) => {
                const dot = document.createElement('div');
                dot.className = 'nav-dot' + (index === this.currentIndex ? ' active' : '');
                dot.addEventListener('click', () => this.goToPhoto(index));
                this.elements.navDots.appendChild(dot);
            });
        }
    }
    
    updateNavDots() {
        const dots = this.elements.navDots.querySelectorAll('.nav-dot');
        dots.forEach((dot, index) => {
            dot.classList.toggle('active', index === this.currentIndex);
            const photoId = this.photos[index].id;
            if (this.cropData[photoId]) {
                dot.classList.add('edited');
            }
        });
    }
    
    async loadPhoto(index) {
        if (index < 0 || index >= this.photos.length) return;
        
        this.saveCropData();
        this.currentIndex = index;
        const photo = this.photos[index];
        
        this.showLoading(true);
        
        if (this.cropper) {
            this.cropper.destroy();
            this.cropper = null;
        }
        
        this.elements.currentIndex.textContent = index + 1;
        this.elements.formatBadge.textContent = photo.product_name || photo.format_name || 'Полароид';
        this.updateConfidenceIndicator(photo);
        this.updateNavigation();
        this.updateNavDots();
        
        try {
            await this.loadImage(photo.url);
            this.initCropper(photo);
            this.showLoading(false);
        } catch (error) {
            console.error('Failed to load image:', error);
            this.showError(true);
        }
    }
    
    loadImage(url) {
        return new Promise((resolve, reject) => {
            const img = this.elements.cropImage;
            img.onload = () => resolve();
            img.onerror = () => reject(new Error('Image load failed'));
            img.src = url;
        });
    }
    
    initCropper(photo) {
        const ratio = photo.aspect_ratio || this.defaultAspectRatio;
        
        this.cropper = new Cropper(this.elements.cropImage, {
            aspectRatio: ratio,
            viewMode: 1,
            dragMode: 'move',
            autoCropArea: 0.9,
            responsive: true,
            restore: false,
            guides: true,
            center: true,
            highlight: true,
            cropBoxMovable: true,
            cropBoxResizable: true,
            toggleDragModeOnDblclick: false,
            
            ready: () => {
                const savedCrop = this.cropData[photo.id];
                if (savedCrop) {
                    this.cropper.setData(savedCrop);
                } else if (photo.auto_crop) {
                    this.cropper.setData(photo.auto_crop);
                }
            },
            
            crop: () => {
                this.elements.hint.classList.add('hidden');
            }
        });
    }
    
    updateConfidenceIndicator(photo) {
        const dot = this.elements.confidenceIndicator.querySelector('.confidence-dot');
        const text = this.elements.confidenceIndicator.querySelector('.confidence-text');
        const confidence = photo.confidence || 0.5;
        const method = photo.method || 'center';
        const facesFound = photo.faces_found || 0;
        
        dot.classList.remove('medium', 'low');
        
        if (method === 'face') {
            if (facesFound === 1) {
                text.textContent = '👤 Лицо найдено';
            } else if (facesFound > 1) {
                dot.classList.add('medium');
                text.textContent = '👥 Найдено ' + facesFound + ' лица';
            }
        } else if (method === 'saliency') {
            dot.classList.add('medium');
            text.textContent = '🎯 Авто-фокус';
        } else {
            if (confidence >= 0.8) {
                text.textContent = 'По центру';
            } else {
                dot.classList.add('low');
                text.textContent = 'Проверьте кадр';
            }
        }
        
        if (confidence < 0.5) {
            dot.classList.add('low');
        } else if (confidence < 0.8) {
            dot.classList.add('medium');
        }
    }
    
    updateNavigation() {
        this.elements.btnPrev.disabled = this.currentIndex === 0;
        this.elements.btnNext.disabled = this.currentIndex === this.photos.length - 1;
    }
    
    showLoading(show) {
        this.isLoading = show;
        this.elements.loading.classList.toggle('hidden', !show);
        this.elements.errorState.style.display = 'none';
    }
    
    showError(show) {
        this.elements.loading.classList.add('hidden');
        this.elements.errorState.style.display = show ? 'flex' : 'none';
    }
    
    saveCropData() {
        if (!this.cropper) return;
        
        const photo = this.photos[this.currentIndex];
        const data = this.cropper.getData(true);
        
        this.cropData[photo.id] = {
            x: data.x,
            y: data.y,
            width: data.width,
            height: data.height,
            rotate: data.rotate,
            scaleX: data.scaleX,
            scaleY: data.scaleY
        };
    }
    
    navigate(direction) {
        const newIndex = this.currentIndex + direction;
        if (newIndex >= 0 && newIndex < this.photos.length) {
            this.loadPhoto(newIndex);
        }
    }
    
    goToPhoto(index) {
        if (index !== this.currentIndex) {
            this.loadPhoto(index);
        }
    }
    
    resetCrop() {
        if (!this.cropper) return;
        
        const photo = this.photos[this.currentIndex];
        
        if (photo.auto_crop) {
            this.cropper.setData(photo.auto_crop);
        } else {
            this.cropper.reset();
        }
        
        delete this.cropData[photo.id];
        this.updateNavDots();
        
        this.showToast('↩️', 'Сброшено');
    }
    
    autoCrop() {
        if (!this.cropper) return;
        
        const photo = this.photos[this.currentIndex];
        
        if (photo.auto_crop) {
            this.cropper.setData(photo.auto_crop);
            this.showToast('🎯', 'Автокадр применён');
        } else {
            this.cropper.reset();
            this.showToast('🎯', 'По центру');
        }
    }
    
    rotate() {
        if (!this.cropper) return;
        this.cropper.rotate(90);
        this.showToast('🔄', 'Повёрнуто');
    }
    
    flip() {
        if (!this.cropper) return;
        const scaleX = this.cropper.getData().scaleX || 1;
        this.cropper.scaleX(-scaleX);
        this.showToast('↔️', 'Отражено');
    }
    
    retryLoad() {
        this.loadPhoto(this.currentIndex);
    }
    
    async saveAll() {
        this.saveCropData();
        
        const result = {
            order_id: this.orderId,
            user_id: this.tg?.initDataUnsafe?.user?.id || null,
            photos: this.photos.map(photo => ({
                id: photo.id,
                crop: this.cropData[photo.id] || photo.auto_crop || null
            }))
        };
        
        const saveBtn = document.getElementById('btnSave');
        saveBtn.innerHTML = '⏳';
        saveBtn.disabled = true;
        
        try {
            const urlParams = new URLSearchParams(window.location.search);
            const apiBase = urlParams.get('api_url') || 'http://localhost:8080';
            
            const response = await fetch(apiBase + '/api/crop/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(result)
            });
            
            if (response.ok) {
                saveBtn.innerHTML = '✅';
                this.showToast('✅', 'Сохранено!');
                
                setTimeout(() => {
                    if (this.tg && this.tg.close) {
                        this.tg.close();
                    } else {
                        this.showToast('ℹ️', 'Закройте окно');
                    }
                }, 1000);
            } else {
                const error = await response.text();
                throw new Error(error || 'API error');
            }
        } catch (e) {
            console.error('Save error:', e);
            saveBtn.innerHTML = '❌';
            saveBtn.disabled = false;
            this.showToast('❌', 'Ошибка: ' + e.message, 'error');
        }
    }
    
    showToast(icon, text, type = '') {
        const toast = this.elements.toast;
        toast.querySelector('.toast-icon').textContent = icon;
        toast.querySelector('.toast-text').textContent = text;
        toast.className = 'toast visible ' + type;
        
        setTimeout(() => {
            toast.classList.remove('visible');
        }, 2000);
    }
}

let app;
document.addEventListener('DOMContentLoaded', () => {
    app = new PhotoCropperApp();
});
