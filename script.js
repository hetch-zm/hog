// ============================================================================
// Hope of Glory · home page interactions
// ============================================================================

const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// ---------- Mobile navigation ---------------------------------------------
const navToggle = document.getElementById('navToggle');
const navMenu = document.getElementById('navMenu');

if (navToggle && navMenu) {
    navToggle.addEventListener('click', () => {
        const open = navMenu.classList.toggle('active');
        navToggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
}

const navLinks = document.querySelectorAll('.nav-link');
navLinks.forEach(link => {
    link.addEventListener('click', () => {
        if (navMenu) navMenu.classList.remove('active');
        if (navToggle) navToggle.setAttribute('aria-expanded', 'false');
    });
});

// ---------- Smooth-scroll anchor links ------------------------------------
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        const href = this.getAttribute('href');
        if (href === '#' || href.length < 2) return;
        const target = document.querySelector(href);
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'start' });
    });
});

// ---------- Active nav link on scroll -------------------------------------
const sections = document.querySelectorAll('section[id]');
function updateActiveNavLink() {
    const scrollPosition = window.scrollY + 100;
    sections.forEach(section => {
        const top = section.offsetTop;
        const height = section.offsetHeight;
        const id = section.getAttribute('id');
        if (scrollPosition >= top && scrollPosition < top + height) {
            navLinks.forEach(link => {
                link.classList.toggle('active', link.getAttribute('href') === `#${id}`);
            });
        }
    });
}

// ---------- Navbar shadow on scroll ---------------------------------------
const navbar = document.getElementById('navbar');
function updateNavbarShadow() {
    if (!navbar) return;
    navbar.classList.toggle('scrolled', window.scrollY > 12);
}

let scrollRaf = null;
window.addEventListener('scroll', () => {
    if (scrollRaf) return;
    scrollRaf = requestAnimationFrame(() => {
        updateActiveNavLink();
        updateNavbarShadow();
        scrollRaf = null;
    });
}, { passive: true });
updateNavbarShadow();

// ---------- Contact form (placeholder) ------------------------------------
const contactForm = document.getElementById('contactForm');
if (contactForm) {
    contactForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const name = document.getElementById('name').value;
        const email = document.getElementById('email').value;
        alert(`Thank you, ${name}! Your message has been received. We'll get back to you soon at ${email}.`);
        contactForm.reset();
    });
}

// ---------- Fade-in on scroll for cards -----------------------------------
if (!prefersReducedMotion && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.style.opacity = '1';
                entry.target.style.transform = 'translateY(0)';
                observer.unobserve(entry.target);
            }
        });
    }, { threshold: 0.12, rootMargin: '0px 0px -40px 0px' });

    document.querySelectorAll('.time-card, .ministry-card, .event-card, .strat-card, .welcome-text, .welcome-image').forEach((el, i) => {
        el.style.opacity = '0';
        el.style.transform = 'translateY(20px)';
        el.style.transition = `opacity .55s ease ${(i % 6) * 0.05}s, transform .55s ease ${(i % 6) * 0.05}s`;
        observer.observe(el);
    });
}

// ---------- Stat counters (count up on scroll into view) ------------------
const statEls = document.querySelectorAll('.stat[data-count]');
if (statEls.length && 'IntersectionObserver' in window) {
    const animate = (el) => {
        const target = parseInt(el.getAttribute('data-count'), 10) || 0;
        const counter = el.querySelector('.counter');
        if (!counter) return;
        if (prefersReducedMotion) { counter.textContent = target; return; }
        const duration = 1100;
        const start = performance.now();
        const tick = (now) => {
            const t = Math.min(1, (now - start) / duration);
            const eased = 1 - Math.pow(1 - t, 3); // ease-out cubic
            counter.textContent = Math.round(target * eased);
            if (t < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    };
    const statObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                animate(entry.target);
                statObserver.unobserve(entry.target);
            }
        });
    }, { threshold: 0.4 });
    statEls.forEach(el => statObserver.observe(el));
}

// ---------- Year stamp in footer ------------------------------------------
const copyrightText = document.querySelector('.footer-bottom p');
if (copyrightText) {
    copyrightText.textContent = copyrightText.textContent.replace(/\d{4}/, new Date().getFullYear());
}

// ---------- Payment modal --------------------------------------------------
const paymentModal = document.getElementById('paymentModal');
const partnerBtn = document.getElementById('partnerBtn');
const closePaymentModalBtn = document.querySelector('.close-modal');

function openModal(modal) {
    if (!modal) return;
    modal.style.display = 'block';
    document.body.style.overflow = 'hidden';
}
function closeModal(modal) {
    if (!modal) return;
    modal.style.display = 'none';
    document.body.style.overflow = '';
}

if (partnerBtn) partnerBtn.addEventListener('click', (e) => { e.preventDefault(); openModal(paymentModal); });
if (closePaymentModalBtn) closePaymentModalBtn.addEventListener('click', () => closeModal(paymentModal));

// ---------- Farm modal -----------------------------------------------------
const farmModal = document.getElementById('farmModal');
const churchFarmCard = document.getElementById('churchFarmCard');
const closeFarmModalBtn = document.querySelector('.close-farm-modal');
const mainFarmImage = document.getElementById('mainFarmImage');
const farmThumbs = document.querySelectorAll('.farm-thumb');

if (churchFarmCard) churchFarmCard.addEventListener('click', () => openModal(farmModal));
if (closeFarmModalBtn) closeFarmModalBtn.addEventListener('click', () => closeModal(farmModal));

window.addEventListener('click', (e) => {
    if (e.target === paymentModal) closeModal(paymentModal);
    if (e.target === farmModal) closeModal(farmModal);
});
document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    if (paymentModal && paymentModal.style.display === 'block') closeModal(paymentModal);
    if (farmModal && farmModal.style.display === 'block') closeModal(farmModal);
});

farmThumbs.forEach(thumb => {
    thumb.addEventListener('click', () => {
        const imgSrc = thumb.querySelector('img').src;
        if (mainFarmImage) {
            mainFarmImage.style.opacity = '0';
            setTimeout(() => {
                mainFarmImage.src = imgSrc;
                mainFarmImage.style.opacity = '1';
            }, 180);
        }
        farmThumbs.forEach(t => t.classList.remove('active'));
        thumb.classList.add('active');
    });
});
if (mainFarmImage) mainFarmImage.style.transition = 'opacity .25s ease';

// ---------- Gallery --------------------------------------------------------
const mainGalleryImage = document.getElementById('mainGalleryImage');
const galleryThumbs = document.querySelectorAll('.gallery-thumb');
const galleryScrollStrip = document.getElementById('galleryScrollStrip');
const scrollLeftBtn = document.getElementById('scrollLeft');
const scrollRightBtn = document.getElementById('scrollRight');

function updateMainImage(thumb) {
    const imgSrc = thumb.querySelector('img').src;
    if (mainGalleryImage) {
        mainGalleryImage.style.opacity = '0';
        setTimeout(() => {
            mainGalleryImage.src = imgSrc;
            mainGalleryImage.style.opacity = '1';
        }, 180);
    }
    galleryThumbs.forEach(t => t.classList.remove('active'));
    thumb.classList.add('active');
}
galleryThumbs.forEach(thumb => {
    thumb.addEventListener('click', () => {
        updateMainImage(thumb);
        thumb.scrollIntoView({ behavior: prefersReducedMotion ? 'auto' : 'smooth', block: 'nearest', inline: 'center' });
    });
});

let galleryScrollTimeout = null;
if (galleryScrollStrip) {
    galleryScrollStrip.addEventListener('scroll', () => {
        clearTimeout(galleryScrollTimeout);
        galleryScrollTimeout = setTimeout(() => {
            const scrollLeft = galleryScrollStrip.scrollLeft;
            const containerWidth = galleryScrollStrip.offsetWidth;
            const centerPosition = scrollLeft + (containerWidth / 2);
            let closest = null;
            let closestDistance = Infinity;
            galleryThumbs.forEach(thumb => {
                const center = thumb.offsetLeft + thumb.offsetWidth / 2;
                const distance = Math.abs(centerPosition - center);
                if (distance < closestDistance) { closestDistance = distance; closest = thumb; }
            });
            if (closest) updateMainImage(closest);
        }, 150);
    }, { passive: true });
}

if (scrollLeftBtn && galleryScrollStrip)
    scrollLeftBtn.addEventListener('click', () => galleryScrollStrip.scrollBy({ left: -360, behavior: prefersReducedMotion ? 'auto' : 'smooth' }));
if (scrollRightBtn && galleryScrollStrip)
    scrollRightBtn.addEventListener('click', () => galleryScrollStrip.scrollBy({ left: 360, behavior: prefersReducedMotion ? 'auto' : 'smooth' }));
if (mainGalleryImage) mainGalleryImage.style.transition = 'opacity .25s ease';

// ---------- Hero slideshow ------------------------------------------------
(function () {
    const slides = document.querySelectorAll('.hero-slide');
    const dots = document.querySelectorAll('.hero-dot');
    const hero = document.querySelector('.hero');
    if (!slides.length || !dots.length) return;

    let current = 0;
    let interval = null;

    function go(i) {
        slides[current].classList.remove('active');
        dots[current].classList.remove('active');
        current = (i + slides.length) % slides.length;
        slides[current].classList.add('active');
        dots[current].classList.add('active');
    }
    function next() { go(current + 1); }
    function start() { stop(); interval = setInterval(next, 5500); }
    function stop()  { if (interval) { clearInterval(interval); interval = null; } }

    dots.forEach((dot, i) => {
        dot.addEventListener('click', () => { go(i); start(); });
    });
    if (hero) {
        hero.addEventListener('mouseenter', stop);
        hero.addEventListener('mouseleave', start);
    }
    if (!prefersReducedMotion) start();
})();
