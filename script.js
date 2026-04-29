// Mobile Navigation Toggle
const navToggle = document.getElementById('navToggle');
const navMenu = document.getElementById('navMenu');

navToggle.addEventListener('click', () => {
    navMenu.classList.toggle('active');
});

// Close mobile menu when clicking a link
const navLinks = document.querySelectorAll('.nav-link');
navLinks.forEach(link => {
    link.addEventListener('click', () => {
        navMenu.classList.remove('active');
    });
});

// Smooth scroll with offset for fixed navbar
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            const offset = 80;
            const targetPosition = target.offsetTop - offset;
            window.scrollTo({
                top: targetPosition,
                behavior: 'smooth'
            });
        }
    });
});

// Active navigation link on scroll
function updateActiveNavLink() {
    const sections = document.querySelectorAll('section[id]');
    const scrollPosition = window.scrollY + 100;

    sections.forEach(section => {
        const sectionTop = section.offsetTop;
        const sectionHeight = section.offsetHeight;
        const sectionId = section.getAttribute('id');

        if (scrollPosition >= sectionTop && scrollPosition < sectionTop + sectionHeight) {
            navLinks.forEach(link => {
                link.classList.remove('active');
                if (link.getAttribute('href') === `#${sectionId}`) {
                    link.classList.add('active');
                }
            });
        }
    });
}

window.addEventListener('scroll', updateActiveNavLink);

// Navbar background change on scroll
const navbar = document.querySelector('.navbar');
window.addEventListener('scroll', () => {
    if (window.scrollY > 50) {
        navbar.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.15)';
    } else {
        navbar.style.boxShadow = '0 2px 10px rgba(0, 0, 0, 0.1)';
    }
});

// Contact form handling
const contactForm = document.getElementById('contactForm');
contactForm.addEventListener('submit', (e) => {
    e.preventDefault();

    const name = document.getElementById('name').value;
    const email = document.getElementById('email').value;
    const phone = document.getElementById('phone').value;
    const message = document.getElementById('message').value;

    // In a real application, you would send this data to a server
    // For now, we'll just show an alert
    alert(`Thank you, ${name}! Your message has been received. We'll get back to you soon at ${email}.`);

    // Reset form
    contactForm.reset();
});

// Intersection Observer for fade-in animations
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -50px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.style.opacity = '1';
            entry.target.style.transform = 'translateY(0)';
        }
    });
}, observerOptions);

// Apply fade-in animation to elements
const animateElements = document.querySelectorAll('.time-card, .ministry-card, .event-card, .welcome-text, .welcome-image');
animateElements.forEach(el => {
    el.style.opacity = '0';
    el.style.transform = 'translateY(30px)';
    el.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
    observer.observe(el);
});

// Add entrance animation delay to cards
document.querySelectorAll('.ministry-card').forEach((card, index) => {
    card.style.transitionDelay = `${index * 0.1}s`;
});

document.querySelectorAll('.time-card').forEach((card, index) => {
    card.style.transitionDelay = `${index * 0.15}s`;
});

// Auto-hide scroll indicator
window.addEventListener('scroll', () => {
    const scrollIndicator = document.querySelector('.scroll-indicator');
    if (window.scrollY > 100) {
        scrollIndicator.style.opacity = '0';
    } else {
        scrollIndicator.style.opacity = '1';
    }
});

// Smooth entrance for hero content
window.addEventListener('load', () => {
    const heroContent = document.querySelector('.hero-content');
    heroContent.style.animation = 'fadeInUp 1s ease';
});

// Add hover effect to buttons
const buttons = document.querySelectorAll('.btn');
buttons.forEach(btn => {
    btn.addEventListener('mouseenter', function() {
        this.style.transform = 'translateY(-3px)';
    });

    btn.addEventListener('mouseleave', function() {
        this.style.transform = 'translateY(0)';
    });
});

// Parallax effect for hero section (subtle)
window.addEventListener('scroll', () => {
    const scrolled = window.pageYOffset;
    const hero = document.querySelector('.hero-content');
    if (hero) {
        hero.style.transform = `translateY(${scrolled * 0.3}px)`;
    }
});

// Add loading class to body
document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('loaded');
});

// Form input focus effects
const formInputs = document.querySelectorAll('.form-group input, .form-group textarea');
formInputs.forEach(input => {
    input.addEventListener('focus', function() {
        this.parentElement.classList.add('focused');
    });

    input.addEventListener('blur', function() {
        if (this.value === '') {
            this.parentElement.classList.remove('focused');
        }
    });
});

// Dynamic year for copyright
const currentYear = new Date().getFullYear();
const copyrightText = document.querySelector('.footer-bottom p');
if (copyrightText) {
    copyrightText.textContent = copyrightText.textContent.replace('2024', currentYear);
}

// Payment Modal Functionality
const paymentModal = document.getElementById('paymentModal');
const partnerBtn = document.getElementById('partnerBtn');
const closeModal = document.querySelector('.close-modal');

// Open modal when Partner button is clicked
if (partnerBtn) {
    partnerBtn.addEventListener('click', (e) => {
        e.preventDefault();
        paymentModal.style.display = 'block';
        document.body.style.overflow = 'hidden'; // Prevent background scrolling
    });
}

// Close modal when X is clicked
if (closeModal) {
    closeModal.addEventListener('click', () => {
        paymentModal.style.display = 'none';
        document.body.style.overflow = 'auto'; // Restore scrolling
    });
}

// Close modal when clicking outside of it
window.addEventListener('click', (e) => {
    if (e.target === paymentModal) {
        paymentModal.style.display = 'none';
        document.body.style.overflow = 'auto'; // Restore scrolling
    }
});

// Close modal with Escape key
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && paymentModal.style.display === 'block') {
        paymentModal.style.display = 'none';
        document.body.style.overflow = 'auto'; // Restore scrolling
    }
});

// Gallery Functionality
const mainGalleryImage = document.getElementById('mainGalleryImage');
const galleryThumbs = document.querySelectorAll('.gallery-thumb');
const galleryScrollStrip = document.getElementById('galleryScrollStrip');
const scrollLeftBtn = document.getElementById('scrollLeft');
const scrollRightBtn = document.getElementById('scrollRight');

// Function to update main image
function updateMainImage(thumb) {
    const imgSrc = thumb.querySelector('img').src;

    // Update main image with fade effect
    mainGalleryImage.style.opacity = '0';
    setTimeout(() => {
        mainGalleryImage.src = imgSrc;
        mainGalleryImage.style.opacity = '1';
    }, 200);

    // Remove active class from all thumbs
    galleryThumbs.forEach(t => t.classList.remove('active'));

    // Add active class to current thumb
    thumb.classList.add('active');
}

// Click on thumbnail to change main image
galleryThumbs.forEach((thumb) => {
    thumb.addEventListener('click', () => {
        updateMainImage(thumb);
        // Scroll the thumbnail into view
        thumb.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
    });
});

// Auto-update main image based on scroll position
let scrollTimeout;
if (galleryScrollStrip) {
    galleryScrollStrip.addEventListener('scroll', () => {
        // Clear previous timeout
        clearTimeout(scrollTimeout);

        // Set new timeout to detect when scrolling stops
        scrollTimeout = setTimeout(() => {
            // Get the scroll position
            const scrollLeft = galleryScrollStrip.scrollLeft;
            const containerWidth = galleryScrollStrip.offsetWidth;
            const centerPosition = scrollLeft + (containerWidth / 2);

            // Find the thumbnail closest to center
            let closestThumb = null;
            let closestDistance = Infinity;

            galleryThumbs.forEach((thumb) => {
                const thumbLeft = thumb.offsetLeft;
                const thumbCenter = thumbLeft + (thumb.offsetWidth / 2);
                const distance = Math.abs(centerPosition - thumbCenter);

                if (distance < closestDistance) {
                    closestDistance = distance;
                    closestThumb = thumb;
                }
            });

            // Update main image to the closest thumbnail
            if (closestThumb) {
                updateMainImage(closestThumb);
            }
        }, 150); // Wait 150ms after scrolling stops
    });
}

// Scroll buttons functionality
if (scrollLeftBtn) {
    scrollLeftBtn.addEventListener('click', () => {
        galleryScrollStrip.scrollBy({ left: -400, behavior: 'smooth' });
    });
}

if (scrollRightBtn) {
    scrollRightBtn.addEventListener('click', () => {
        galleryScrollStrip.scrollBy({ left: 400, behavior: 'smooth' });
    });
}

// Add transition to main image
if (mainGalleryImage) {
    mainGalleryImage.style.transition = 'opacity 0.3s ease';
}

// Farm Modal Functionality
const farmModal = document.getElementById('farmModal');
const churchFarmCard = document.getElementById('churchFarmCard');
const closeFarmModal = document.querySelector('.close-farm-modal');
const mainFarmImage = document.getElementById('mainFarmImage');
const farmThumbs = document.querySelectorAll('.farm-thumb');

// Open farm modal when clicking the card or button
if (churchFarmCard) {
    churchFarmCard.addEventListener('click', (e) => {
        farmModal.style.display = 'block';
        document.body.style.overflow = 'hidden';
    });
}

// Close farm modal when X is clicked
if (closeFarmModal) {
    closeFarmModal.addEventListener('click', () => {
        farmModal.style.display = 'none';
        document.body.style.overflow = 'auto';
    });
}

// Close farm modal when clicking outside
window.addEventListener('click', (e) => {
    if (e.target === farmModal) {
        farmModal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
});

// Farm thumbnail click functionality
farmThumbs.forEach((thumb) => {
    thumb.addEventListener('click', () => {
        const imgSrc = thumb.querySelector('img').src;

        // Update main farm image with fade effect
        if (mainFarmImage) {
            mainFarmImage.style.opacity = '0';
            setTimeout(() => {
                mainFarmImage.src = imgSrc;
                mainFarmImage.style.opacity = '1';
            }, 200);
        }

        // Remove active class from all farm thumbs
        farmThumbs.forEach(t => t.classList.remove('active'));

        // Add active class to clicked thumb
        thumb.classList.add('active');
    });
});

// Add transition to main farm image
if (mainFarmImage) {
    mainFarmImage.style.transition = 'opacity 0.3s ease';
}

// Slideshow Functionality
(function() {
    const slides = document.querySelectorAll('.slideshow-slide');
    const dots = document.querySelectorAll('.slideshow-dot');
    const slideshow = document.querySelector('.slideshow');
    if (!slides.length || !dots.length) return;

    let currentSlide = 0;
    let intervalId = null;

    function goToSlide(index) {
        slides[currentSlide].classList.remove('active');
        dots[currentSlide].classList.remove('active');
        currentSlide = index;
        slides[currentSlide].classList.add('active');
        dots[currentSlide].classList.add('active');
    }

    function nextSlide() {
        goToSlide((currentSlide + 1) % slides.length);
    }

    function startAutoPlay() {
        intervalId = setInterval(nextSlide, 5000);
    }

    function stopAutoPlay() {
        clearInterval(intervalId);
    }

    // Dot click navigation
    dots.forEach(function(dot, index) {
        dot.addEventListener('click', function() {
            stopAutoPlay();
            goToSlide(index);
            startAutoPlay();
        });
    });

    // Pause on hover
    if (slideshow) {
        slideshow.addEventListener('mouseenter', stopAutoPlay);
        slideshow.addEventListener('mouseleave', startAutoPlay);
    }

    // Start auto-rotation
    startAutoPlay();
})();