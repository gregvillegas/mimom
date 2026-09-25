document.addEventListener("DOMContentLoaded", function () {
    var toastElList = [].slice.call(document.querySelectorAll(".toast"));
    toastElList.forEach(function (toastEl) {
        var toast = new bootstrap.Toast(toastEl, {
            autohide: true,
            delay: 5000,
        });
        toast.show();
    });

    document.querySelectorAll('form[data-confirm]').forEach(function (form) {
        form.addEventListener("submit", function (event) {
            var message = form.getAttribute("data-confirm") || "Are you sure?";
            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    document.querySelectorAll('a[data-confirm]').forEach(function (link) {
        link.addEventListener("click", function (event) {
            var message = link.getAttribute("data-confirm") || "Are you sure?";
            if (!window.confirm(message)) {
                event.preventDefault();
            }
        });
    });

    var tooltips = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltips.forEach(function (el) {
        new bootstrap.Tooltip(el);
    });

    window.addEventListener("beforeunload", function () {
        // no-op hook for page-specific unsaved-change warnings
    });
});

window.IntranetUI = {
    showToast: function (message, variant, delay) {
        variant = variant || 'info';
        delay = delay || 4000;

        var container = document.querySelector('.toast-container');
        if (!container) {
            container = document.createElement('div');
            container.className = 'toast-container position-fixed top-0 end-0 p-3';
            container.style.top = '100px';
            container.style.zIndex = '1090';
            document.body.appendChild(container);
        }

        var toastEl = document.createElement('div');
        toastEl.className = 'toast text-bg-' + variant + ' border-0';
        toastEl.setAttribute('role', 'alert');
        toastEl.setAttribute('aria-live', 'assertive');
        toastEl.setAttribute('aria-atomic', 'true');

        var closeBtnVariant = (variant === 'light' || variant === 'warning' || variant === 'info') ? 'btn-close-dark' : 'btn-close-white';

        toastEl.innerHTML =
            '<div class="d-flex">' +
                '<div class="toast-body">' + message + '</div>' +
                '<button type="button" class="btn-close ' + closeBtnVariant + ' me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>' +
            '</div>';

        container.appendChild(toastEl);
        var toast = new bootstrap.Toast(toastEl, { autohide: true, delay: delay });
        toast.show();
        toastEl.addEventListener('hidden.bs.toast', function () {
            toastEl.remove();
        });
        return toast;
    },

    confirmDialog: function (options) {
        options = options || {};
        var title = options.title || 'Confirm';
        var message = options.message || 'Are you sure?';
        var confirmText = options.confirmText || 'Confirm';
        var cancelText = options.cancelText || 'Cancel';
        var variant = options.variant || 'danger';
        var onConfirm = options.onConfirm || null;

        return new Promise(function (resolve) {
            var modalEl = document.getElementById('confirmDialogModal');
            if (!modalEl) {
                var modalHtml =
                    '<div class="modal fade" id="confirmDialogModal" tabindex="-1" aria-labelledby="confirmDialogModalLabel" aria-hidden="true">' +
                        '<div class="modal-dialog modal-dialog-centered">' +
                            '<div class="modal-content">' +
                                '<div class="modal-header">' +
                                    '<h1 class="modal-title h5 fw-semibold" id="confirmDialogModalLabel">Confirm</h1>' +
                                    '<button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>' +
                                '</div>' +
                                '<div class="modal-body" id="confirmDialogModalBody">Are you sure?</div>' +
                                '<div class="modal-footer">' +
                                    '<button type="button" class="btn btn-secondary" data-bs-dismiss="modal" id="confirmDialogCancelBtn">Cancel</button>' +
                                    '<button type="button" class="btn btn-danger" id="confirmDialogConfirmBtn">Confirm</button>' +
                                '</div>' +
                            '</div>' +
                        '</div>' +
                    '</div>';
                var wrapper = document.createElement('div');
                wrapper.innerHTML = modalHtml;
                document.body.appendChild(wrapper.firstElementChild);
                modalEl = document.getElementById('confirmDialogModal');
            }

            var titleEl = modalEl.querySelector('#confirmDialogModalLabel');
            var bodyEl = modalEl.querySelector('#confirmDialogModalBody');
            var cancelBtn = modalEl.querySelector('#confirmDialogCancelBtn');
            var confirmBtn = modalEl.querySelector('#confirmDialogConfirmBtn');

            titleEl.textContent = title;
            bodyEl.innerHTML = message;
            cancelBtn.textContent = cancelText;
            confirmBtn.textContent = confirmText;

            confirmBtn.className = 'btn btn-' + variant;

            var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            var confirmed = false;

            function confirmHandler() {
                confirmed = true;
                modal.hide();
            }

            function hiddenHandler() {
                confirmBtn.removeEventListener('click', confirmHandler);
                modalEl.removeEventListener('hidden.bs.modal', hiddenHandler);
                if (confirmed) {
                    if (typeof onConfirm === 'function') {
                        onConfirm();
                    }
                    resolve(true);
                } else {
                    resolve(false);
                }
            }

            confirmBtn.addEventListener('click', confirmHandler);
            modalEl.addEventListener('hidden.bs.modal', hiddenHandler);

            modal.show();
        });
    },

    setFieldInvalid: function (formId, fieldName, errorText) {
        var form = document.getElementById(formId);
        if (!form) return;
        var field = form.querySelector('[name="' + fieldName + '"]');
        if (!field) return;

        field.classList.add('is-invalid');
        var formGroup = field.closest('.mb-3, .form-group, .col, [class*="col-"]');
        if (!formGroup) {
            formGroup = field.parentNode;
        }

        var existingFeedback = formGroup.querySelector('.invalid-feedback[data-field="' + fieldName + '"]');
        if (existingFeedback) {
            existingFeedback.textContent = errorText;
            existingFeedback.style.display = 'block';
            return;
        }

        var feedback = document.createElement('div');
        feedback.className = 'invalid-feedback';
        feedback.setAttribute('data-field', fieldName);
        feedback.style.display = 'block';
        feedback.textContent = errorText;
        field.parentNode.insertBefore(feedback, field.nextSibling);
    },

    setValidationSummary: function (formId, errors) {
        errors = errors || [];
        var form = document.getElementById(formId);
        if (!form) return;

        var summaryId = formId + '-validation-summary';
        var summary = document.getElementById(summaryId);

        if (!errors.length) {
            if (summary) summary.remove();
            return;
        }

        if (!summary) {
            summary = document.createElement('div');
            summary.id = summaryId;
            summary.className = 'alert alert-danger d-flex align-items-start gap-2';
            summary.setAttribute('role', 'alert');
            form.insertBefore(summary, form.firstChild);
        }

        var listHtml = '<ul class="mb-0 ps-3">';
        for (var i = 0; i < errors.length; i++) {
            listHtml += '<li>' + errors[i] + '</li>';
        }
        listHtml += '</ul>';

        summary.innerHTML =
            '<i class="bi bi-exclamation-triangle-fill mt-1"></i>' +
            '<div><strong class="d-block mb-1">Please correct the following errors:</strong>' + listHtml + '</div>';
    },

    autoCloseAlerts: function () {
        var alerts = document.querySelectorAll('.alert.alert-dismissible');
        alerts.forEach(function (alertEl) {
            setTimeout(function () {
                var bsAlert = bootstrap.Alert.getOrCreateInstance(alertEl);
                if (bsAlert) bsAlert.close();
            }, 6000);
        });
    },

    stickySubmitBarInit: function () {
        var bars = document.querySelectorAll('.sticky-submit-bar');
        bars.forEach(function (bar) {
            if (bar.dataset.intranetStickyInit === '1') return;
            bar.dataset.intranetStickyInit = '1';

            var form = bar.closest('form');
            if (!form) return;

            var placeholder = document.createElement('div');
            placeholder.style.height = bar.offsetHeight + 'px';
            placeholder.style.display = 'none';
            bar.parentNode.insertBefore(placeholder, bar);

            var observer = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    if (entry.isIntersecting) {
                        placeholder.style.display = 'none';
                    } else {
                        placeholder.style.display = 'block';
                    }
                });
            }, { root: null, threshold: 0, rootMargin: '0px' });

            observer.observe(bar);
        });
    },

    mobileCardsInit: function () {
        var wraps = document.querySelectorAll('.scrollable-table-wrap');
        wraps.forEach(function (wrap) {
            var tables = wrap.querySelectorAll('table');
            tables.forEach(function (table) {
                if (window.innerWidth < 768) {
                    table.classList.add('card-table-mobile');

                    if (!table.dataset.intranetMobileLabelsApplied) {
                        table.dataset.intranetMobileLabelsApplied = '1';
                        var headers = [];
                        var ths = table.querySelectorAll('thead th');
                        ths.forEach(function (th) {
                            headers.push(th.textContent.trim());
                        });
                        var rows = table.querySelectorAll('tbody tr');
                        rows.forEach(function (row) {
                            var tds = row.querySelectorAll('td');
                            tds.forEach(function (td, idx) {
                                if (!td.hasAttribute('data-label') && headers[idx]) {
                                    td.setAttribute('data-label', headers[idx]);
                                }
                            });
                        });
                    }
                } else {
                    table.classList.remove('card-table-mobile');
                }
            });
        });
    },

    offcanvasAutoCloseOnLink: function () {
        var offcanvases = document.querySelectorAll('.offcanvas');
        offcanvases.forEach(function (offcanvasEl) {
            var links = offcanvasEl.querySelectorAll('a.nav-link, a.list-group-item, a[href]:not([data-bs-toggle])');
            links.forEach(function (link) {
                link.addEventListener('click', function (e) {
                    if (link.getAttribute('href') && link.getAttribute('href') !== '#') {
                        var bsOffcanvas = bootstrap.Offcanvas.getInstance(offcanvasEl);
                        if (bsOffcanvas) {
                            bsOffcanvas.hide();
                        }
                    }
                });
            });
        });
    },

    sidebarCollapseInit: function () {
        var sidebar = document.getElementById('sidebarNav');
        var body = document.body;
        if (!sidebar) return;

        var storageKey = 'intranet.sidebar.collapsed';
        var stored = localStorage.getItem(storageKey);
        var isCollapsed = stored === '1';

        if (isCollapsed) {
            sidebar.classList.add('sidebar-collapsed');
            body.classList.add('sidebar-collapsed-lg');
        }

        var toggleBtns = document.querySelectorAll('[data-intranet-sidebar-collapse]');
        toggleBtns.forEach(function (btn) {
            btn.setAttribute('aria-expanded', String(!isCollapsed));

            btn.addEventListener('click', function () {
                var currentlyCollapsed = sidebar.classList.contains('sidebar-collapsed');
                var nextCollapsed = !currentlyCollapsed;

                if (nextCollapsed) {
                    sidebar.classList.add('sidebar-collapsed');
                    body.classList.add('sidebar-collapsed-lg');
                    localStorage.setItem(storageKey, '1');
                } else {
                    sidebar.classList.remove('sidebar-collapsed');
                    body.classList.remove('sidebar-collapsed-lg');
                    localStorage.setItem(storageKey, '0');
                }

                toggleBtns.forEach(function (b) {
                    b.setAttribute('aria-expanded', String(!nextCollapsed));
                });
            });
        });
    },

    initAll: function () {
        window.IntranetUI.autoCloseAlerts();
        window.IntranetUI.stickySubmitBarInit();
        window.IntranetUI.mobileCardsInit();
        window.IntranetUI.offcanvasAutoCloseOnLink();
        window.IntranetUI.sidebarCollapseInit();

        window.addEventListener('resize', function () {
            window.IntranetUI.mobileCardsInit();
        });
    }
};

window.IntranetUI.initAll();
