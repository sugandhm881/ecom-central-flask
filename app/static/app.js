// --- STATE ---
let allOrders = [];
let performanceData = [];
let adsetPerformanceData = [];
let selectedOrderId = null;
let currentView = 'orders-dashboard';
let activePlatformFilter = 'All';
let insightsPlatformFilter = 'All';
let activeStatusFilter = 'All';
let activeDatePreset = 'today';
let insightsDatePreset = 'last_7_days';
let adPerformanceDatePreset = 'last_7_days';
let adsetDatePreset = 'last_7_days';
let authToken = null;
let currentSortKey = null; // For Adset sorting
let currentSortOrder = "asc"; // For Adset sorting

// --- DOM ELEMENTS ---
let loginView, appView, logoutBtn, notificationEl, notificationMessageEl;
let loginBtn, loginEmailEl, loginPasswordEl;
let navOrdersDashboard, navOrderInsights, navAdPerformance, navAdsetBreakdown, navSettings;
let ordersDashboardView, orderInsightsView, adPerformanceView, adsetBreakdownView, settingsView;
let ordersListEl, statusFilterEl, orderDatePresetFilter, customDateContainer, startDateFilterEl, endDateFilterEl, platformFiltersEl,
    dashboardKpiElements, insightsKpiElements, revenueChartCanvas, platformChartCanvas, paymentChartCanvas,
    insightsDatePresetFilter, insightsCustomDateContainer, insightsStartDateFilterEl, insightsEndDateFilterEl,
    insightsPlatformFiltersEl,
    orderModal, modalBackdrop, modalContent, modalCloseBtn;
let adDatePresetFilter, adCustomDateContainer, adStartDateFilterEl, adEndDateFilterEl, performanceTableBody, adKpiElements, spendRevenueChartCanvas, orderStatusChartCanvas;
let adsetDatePresetFilter, adsetCustomDateContainer, adsetStartDateFilterEl, adsetEndDateFilterEl, adsetPerformanceTableBody, downloadPdfBtn, downloadExcelBtn, adsetDateFilterTypeEl;

let revenueChartInstance, platformChartInstance, paymentChartInstance, spendRevenueChartInstance, orderStatusChartInstance;

// --- STATIC DATA ---
let connections = [
    { name: 'Amazon', status: 'Connected', user: 'seller-amz-123' },
    { name: 'Shopify', status: 'Connected', user: 'my-store.myshopify.com' },
    { name: 'Flipkart', status: 'Not Connected', user: null },
];
const platformLogos = {
    Amazon: 'https://www.vectorlogo.zone/logos/amazon/amazon-icon.svg',
    Flipkart: 'https://brandeps.com/logo-download/F/Flipkart-logo-vector-01.svg',
    Shopify: 'https://www.vectorlogo.zone/logos/shopify/shopify-icon.svg',
};

// --- HELPER FUNCTIONS ---
function showNotification(message, isError = false) {
    if (notificationMessageEl) {
        notificationMessageEl.textContent = message;
        notificationEl.className = `fixed top-5 right-5 z-50 text-white py-3 px-5 rounded-lg shadow-xl ${isError ? 'bg-red-500' : 'bg-slate-900'}`;
        notificationEl.classList.add('show');
        setTimeout(() => { notificationEl.classList.remove('show'); }, 3000);
    }
}
const formatCurrency = (amount) => {
  const value = Math.round(parseFloat(amount) || 0);
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(value);
};
const formatNumber = (num) => new Intl.NumberFormat('en-IN').format(num);
const formatPercent = (num) => isFinite(num) ? `${(num * 100).toFixed(1)}%` : '0.0%';
function getStatusBadge(status) {
    switch (status) {
        case 'New': return 'bg-blue-100 text-blue-800';
        case 'Processing': return 'bg-yellow-100 text-yellow-800';
        case 'Shipped': return 'bg-green-100 text-green-800';
        case 'Cancelled': return 'bg-slate-200 text-slate-600';
        default: return 'bg-slate-100 text-slate-800';
    }
}
function createFallbackImage(itemName) {
    const initials = (itemName || 'N/A').split(' ').map(word => word[0]).join('').substring(0, 2).toUpperCase();
    return `https://placehold.co/100x100/e2e8f0/64748b?text=${initials}`;
}

// --- AUTHENTICATION FUNCTIONS ---
async function prefillLoginDetails() {
    try {
        const response = await fetch('/api/get-login-details');
        if (response.ok) {
            const data = await response.json();
            if (loginEmailEl && data.email) {
                loginEmailEl.value = data.email;
            }
            if (loginPasswordEl && data.password) {
                loginPasswordEl.value = data.password;
            }
        }
    } catch (error) {
        console.warn("Could not pre-fill login details. Running in production or server is down.");
    }
}

async function handleLogin() {
    const email = loginEmailEl.value;
    const password = loginPasswordEl.value;

    try {
        const response = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password })
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.message || 'Login failed');
        }
        authToken = data.token;
        localStorage.setItem('authToken', authToken);
        showApp();
    } catch (error) {
        showNotification(error.message, true);
    }
}

function logout() {
    authToken = null;
    localStorage.removeItem('authToken');
    if(loginEmailEl) loginEmailEl.value = '';
    if(loginPasswordEl) loginPasswordEl.value = '';
    showLogin();
}

function showLogin() {
    if (loginView) loginView.style.display = 'flex';
    if (appView) appView.style.display = 'none';
}

function showApp() {
    if (loginView) loginView.style.display = 'none';
    if (appView) appView.style.display = 'flex';
    loadInitialData();
}

// --- API FUNCTIONS ---
function getAuthHeaders() {
    if (!authToken) {
        return {};
    }
    return { "Authorization": `Bearer ${authToken}` };
}

async function fetchApiData(endpoint, errorMessage, options = {}) {
    const headers = { ...getAuthHeaders(), ...options.headers };

    if (!headers.Authorization) {
        showNotification("Please log in to continue.", true);
        logout();
        return Promise.reject("Unauthorized");
    }

    try {
        const response = await fetch(`/api${endpoint}`, { ...options, headers });
        if (response.status === 401) {
            showNotification("Session expired. Please log in again.", true);
            logout();
            return Promise.reject("Unauthorized");
        }
        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || errorData.message || `Server error: ${response.status}`);
        }
        const contentType = response.headers.get('Content-Type');
        const isExcel = contentType && contentType.includes('spreadsheetml.sheet');
        if (contentType && contentType.includes('application/pdf') || isExcel) {
            return await response.blob();
        }
        const text = await response.text();
        return text ? JSON.parse(text) : {};
    } catch (error) {
        console.error(`Client-side API Error in ${endpoint}:`, error);
        showNotification(error.message || errorMessage, true);
        return Promise.reject(error.message);
    }
}

// --- DATA FETCHING & ACTION WRAPPERS ---
const fetchOrdersFromServer = () => fetchApiData(`/get-orders`, 'Failed to fetch orders.');
const fetchAdPerformanceData = (since, until) => fetchApiData(`/get-ad-performance?since=${since}&until=${until}`, 'Failed to fetch ad performance.');
const fetchAdsetPerformanceData = (endpoint) => fetchApiData(endpoint, 'Failed to fetch ad set performance.');

async function createShipment(orderId, platform) {
    showNotification(`Creating shipment for order...`);
    try {
        const result = await fetchApiData('/create-shipment', 'Error creating shipment', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ orderId, platform })
        });
        if (result && result.success) {
            showNotification(`Shipment created! AWB: ${result.awb}`);
            const orderIndex = allOrders.findIndex(o => o.originalId === orderId);
            if (orderIndex !== -1) {
                allOrders[orderIndex].status = result.newStatus;
                allOrders[orderIndex].awb = result.awb;
                renderOrderDetails(allOrders[orderIndex]);
                renderAllDashboard();
            }
        }
    } catch (error) { /* Error is already handled by fetchApiData */ }
}

async function downloadShipmentLabel(awb) {
    if (!awb) {
        showNotification("No AWB number found for this order.", true);
        return;
    }
    showNotification(`Fetching label for AWB: ${awb}...`);
    try {
        const blob = await fetchApiData(`/get-shipping-label?awb=${awb}`, "Failed to download label");
        if (blob) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `label_${awb}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        }
    } catch (err) { /* Error is handled by fetchApiData */ }
}

async function cancelOrder(orderId, platform, orderName) {
    if (!confirm(`Are you sure you want to cancel order ${orderName}?`)) {
        return;
    }
    showNotification(`Cancelling order ${orderName}...`);
    try {
         await fetchApiData('/update-status', 'Error cancelling order', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ orderId, platform, newStatus: 'Cancelled' })
        });
        showNotification("Order cancelled successfully!");
        const orderIndex = allOrders.findIndex(o => o.originalId === orderId);
        if (orderIndex !== -1) {
            allOrders[orderIndex].status = 'Cancelled';
            renderOrderDetails(allOrders[orderIndex]);
            renderAllDashboard();
        }
    } catch(error) { /* Error handled by fetchApiData */ }
}

async function downloadShipmentInvoice(awb, orderId) {
    if (!awb) {
        showNotification("No AWB number found for this order.", true);
        return;
    }
    showNotification(`Fetching invoice for order: ${orderId}...`);
    try {
        const blob = await fetchApiData(`/get-shipping-invoice?awb=${awb}&orderId=${orderId}`, "Failed to download invoice");
        if (blob) {
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `invoice_${orderId ? orderId.replace('#', '') : awb}.pdf`;
            document.body.appendChild(a);
            a.click();
            a.remove();
            window.URL.revokeObjectURL(url);
        }
    } catch (err) { /* Error is handled by fetchApiData */ }
}

// --- UI RENDERING ---
function navigate(view) {
    currentView = view;
    document.querySelectorAll('.sidebar-link').forEach(link => link.classList.remove('active'));
    document.querySelectorAll('main > div[id$="-view"]').forEach(v => v.classList.add('view-hidden'));
    
    let activeLink, activeView;
    switch(view) {
        case 'orders-dashboard': activeLink = navOrdersDashboard; activeView = ordersDashboardView; renderAllDashboard(); break;
        case 'order-insights': activeLink = navOrderInsights; activeView = orderInsightsView; renderAllInsights(); break;
        case 'ad-performance': activeLink = navAdPerformance; activeView = adPerformanceView; handleAdPerformanceDateChange(); break;
        case 'adset-breakdown': activeLink = navAdsetBreakdown; activeView = adsetBreakdownView; handleAdsetDateChange(); break;
        case 'settings': activeLink = navSettings; activeView = settingsView; renderSettings(); break;
    }
    if (activeLink) activeLink.classList.add('active');
    if (activeView) activeView.classList.remove('view-hidden');
}

function renderOrderDetails(order) {
    if (!order) return;
    
    const orderItems = order.line_items || order.items || [];
    
    const itemsHtml = orderItems.map(item => {
        const itemName = item.title || item.name || 'Unknown Item';
        const itemSku = item.sku || 'N/A';
        const itemQty = item.quantity || item.qty || 1;
        
        return `<div class="flex items-center space-x-4">
            <img src="${createFallbackImage(itemName)}" alt="${itemName}" class="w-14 h-14 rounded-lg object-cover bg-slate-200">
            <div class="flex-1">
                <p class="font-semibold text-slate-900">${itemName}</p>
                <p class="text-sm text-slate-500">SKU: ${itemSku}</p>
            </div>
            <p class="text-sm text-slate-500">x ${itemQty}</p>
        </div>`;
    }).join('<hr class="my-3 border-slate-100">');
    
    const customerName = order.buyerName || order.name || 'N/A';
    const customerAddress = order.address || 'No address available';
    
    let primaryActionsHtml = '';
    let secondaryActions = '';
    
    if (order.platform === 'Shopify') {
        if (order.status === 'New' && !order.awb) {
            primaryActionsHtml += `<button id="create-shipment-btn" class="flex-1 w-full px-4 py-2.5 bg-green-600 text-white font-semibold rounded-lg hover:bg-green-700">Create Shipment (RapidShyp)</button>`;
        }
        
        if (order.awb) {
            primaryActionsHtml += `
                <div class="flex gap-2 w-full">
                    <button id="download-label-btn" class="flex-1 px-4 py-2.5 bg-indigo-600 text-white font-semibold rounded-lg hover:bg-indigo-700">Download Label</button>
                    <button id="download-invoice-btn" class="flex-1 px-4 py-2.5 bg-slate-600 text-white font-semibold rounded-lg hover:bg-slate-700">Download Invoice</button>
                </div>
                <p class="text-xs text-center text-slate-500 w-full mt-1">AWB: ${order.awb}</p>
            `;
        }
    }
    
    if (order.status !== 'Shipped' && order.status !== 'Cancelled') {
        secondaryActions += `<a href="#" id="cancel-btn" class="block px-4 py-2 text-sm text-red-600 hover:bg-red-50">Cancel Order</a>`;
    }
    
    modalContent.innerHTML = `
        <h3 class="text-lg font-semibold text-slate-900 mb-4">Order Details (${order.id})</h3>
        <div class="space-y-4">
            <div>
                <h4 class="text-sm font-medium text-slate-500 mb-2">Customer</h4>
                <address class="not-italic text-slate-700">
                    <p class="font-semibold">${customerName}</p>
                    <p class="text-sm">${customerAddress}</p>
                </address>
            </div>
            <div>
                <h4 class="text-sm font-medium text-slate-500 mb-2">Items</h4>
                <div class="space-y-3">${itemsHtml || '<p class="text-sm text-slate-500">No items found</p>'}</div>
            </div>
            <div>
                <h4 class="text-sm font-medium text-slate-500 mb-2">Actions</h4>
                <div class="flex flex-wrap items-center gap-2">
                    ${primaryActionsHtml || '<p class="text-sm text-slate-500">No primary actions available.</p>'}
                    <div class="relative ml-auto">
                        <button id="actions-menu-btn" class="p-2.5 bg-slate-100 text-slate-600 font-semibold rounded-lg hover:bg-slate-200 ${!secondaryActions ? 'hidden' : ''}">
                            <svg class="h-5 w-5" viewBox="0 0 20 20" fill="currentColor"><path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" /></svg>
                        </button>
                        <div id="actions-menu" class="hidden absolute right-0 bottom-full mb-2 w-48 bg-white rounded-lg shadow-xl z-10 py-1 border">${secondaryActions}</div>
                    </div>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('create-shipment-btn')?.addEventListener('click', () => createShipment(order.originalId, order.platform));
    document.getElementById('download-label-btn')?.addEventListener('click', () => downloadShipmentLabel(order.awb));
    document.getElementById('download-invoice-btn')?.addEventListener('click', () => downloadShipmentInvoice(order.awb, order.id));
    document.getElementById('cancel-btn')?.addEventListener('click', (e) => { e.preventDefault(); cancelOrder(order.originalId, order.platform, order.id); });
    document.getElementById('actions-menu-btn')?.addEventListener('click', () => document.getElementById('actions-menu').classList.toggle('hidden'));
}

async function handleAdPerformanceDateChange() {
    const [startDate, endDate] = calculateDateRange(adPerformanceDatePreset, adStartDateFilterEl.value, adEndDateFilterEl.value);
    if (startDate && endDate) {
        const since = startDate.toISOString().split('T')[0];
        const until = endDate.toISOString().split('T')[0];
        try {
            performanceData = await fetchAdPerformanceData(since, until);
            renderAdPerformancePage();
        } catch (error) {}
    }
}

async function handleAdsetDateChange() {
    const [startDate, endDate] = calculateDateRange(adsetDatePreset, adsetStartDateFilterEl.value, adsetEndDateFilterEl.value);
    if (startDate && endDate) {
        const since = startDate.toISOString().split('T')[0];
        const until = endDate.toISOString().split('T')[0];
        const dateFilterType = adsetDateFilterTypeEl ? adsetDateFilterTypeEl.value : 'order_date';
        const endpoint = `/get-adset-performance?since=${since}&until=${until}&date_filter_type=${dateFilterType}`;

        try {
            const response = await fetchAdsetPerformanceData(endpoint);
            adsetPerformanceData = response.adsetPerformance || [];
            
            // Reset sorting when new data is fetched
            currentSortKey = null;
            currentSortOrder = 'asc';
            document.querySelectorAll("#adsetPerformanceTable th.sortable").forEach(th => {
                 const originalText = (th.dataset.originalText || th.textContent.replace(/[▲▼⬍]/g, "")).trim();
                 th.dataset.originalText = originalText;
                 th.textContent = `${originalText} ⬍`;
            });

            renderAdsetPerformanceDashboard();
        } catch (error) { /* Error is handled by fetchApiData */ }
    }
}

function renderAdPerformancePage() {
    renderDailyPerformance();
    renderAdPerformanceCharts();
}

function renderDailyPerformance() {
    const totals = performanceData.reduce((a, d) => (
        a.spend += d.spend,
        a.revenue += d.revenue,
        a.orders += d.totalOrders,
        a.delivered += d.deliveredOrders,
        a.rto += d.rtoOrders,
        a.cancelled += d.cancelledOrders,
        a.deliveredRevenue += (d.deliveredRevenue != null ? d.deliveredRevenue : (d.totalOrders > 0 ? d.revenue * (d.deliveredOrders / d.totalOrders) : 0)),
        a
    ), { spend: 0, revenue: 0, orders: 0, delivered: 0, rto: 0, cancelled: 0, deliveredRevenue: 0 });
    const roas = totals.spend > 0 ? totals.deliveredRevenue / totals.spend : 0;
    const renderKpi = (e, t, v) => {
        e.innerHTML = `<p class="text-sm font-medium text-slate-500">${t}</p><p class="text-3xl font-bold text-slate-800 mt-2">${v}</p>`;
    };
    renderKpi(adKpiElements.totalSpend, 'Total Spend', formatCurrency(totals.spend));
    renderKpi(adKpiElements.totalRevenue, 'Total Revenue', formatCurrency(totals.revenue));
    renderKpi(adKpiElements.roas, 'ROAS', `${roas.toFixed(2)}x`);
    renderKpi(adKpiElements.delivered, 'Delivered', formatNumber(totals.delivered));
    renderKpi(adKpiElements.rto, 'RTO', formatNumber(totals.rto));
    renderKpi(adKpiElements.cancelled, 'Cancelled', formatNumber(totals.cancelled));
    performanceTableBody.innerHTML = '';
    [...performanceData].reverse().forEach(d => {
        const c = d.totalOrders > 0 ? d.spend / d.totalOrders : 0;
        const perDayDeliveredRevenue = (d.deliveredRevenue != null ? d.deliveredRevenue : (d.totalOrders > 0 ? d.revenue * (d.deliveredOrders / d.totalOrders) : 0));
        const r = d.spend > 0 ? perDayDeliveredRevenue / d.spend : 0;

        // Updated RTO% calculation to include Cancelled in numerator and denominator:
        // RTO% = (RTO + Cancelled) / (Delivered + RTO + Cancelled)
        const denom = (d.deliveredOrders || 0) + (d.rtoOrders || 0) + (d.cancelledOrders || 0);
        const rtoPercent = denom > 0 ? (( (d.rtoOrders || 0) + (d.cancelledOrders || 0) ) / denom) : 0;

        performanceTableBody.innerHTML += `<tr class="border-b border-slate-100"><td class="py-3 px-4 font-medium">${new Date(d.date).toLocaleDateString('en-GB', { day: 'short', month: 'short', timeZone: 'UTC' })}</td><td class="py-3 px-4 text-right">${formatCurrency(d.spend)}</td><td class="py-3 px-4 text-right">${formatNumber(d.totalOrders)}</td><td class="py-3 px-4 text-right">${formatCurrency(d.revenue)}</td><td class="py-3 px-4 text-right">${formatCurrency(c)}</td><td class="py-3 px-4 text-right font-semibold">${r.toFixed(2)}x</td><td class="py-3 px-4 text-right text-green-600">${formatNumber(d.deliveredOrders)}</td><td class="py-3 px-4 text-right text-red-600">${formatNumber(d.rtoOrders)}</td><td class="py-3 px-4 text-right text-gray-600">${formatNumber(d.cancelledOrders || 0)}</td><td class="py-3 px-4 text-right text-yellow-600">${formatNumber(d.inTransitOrders || 0)}</td><td class="py-3 px-4 text-right text-blue-600">${formatNumber(d.processingOrders || 0)}</td><td class="py-3 px-4 text-right text-red-600 font-medium">${formatPercent(rtoPercent)}</td></tr>`;
    });
}

function renderAdPerformanceCharts() {
    if (spendRevenueChartInstance) spendRevenueChartInstance.destroy();
    if (orderStatusChartInstance) orderStatusChartInstance.destroy();
    const labels = performanceData.map(d => new Date(d.date).toLocaleDateString('en-GB', { day: 'short', month: 'short', timeZone: 'UTC' }));
    spendRevenueChartInstance = new Chart(spendRevenueChartCanvas, {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'Ad Spend', data: performanceData.map(d => d.spend), borderColor: '#ef4444', backgroundColor: '#fee2e2', fill: true, yAxisID: 'y' },
                { label: 'Revenue', data: performanceData.map(d => d.revenue), borderColor: '#22c55e', backgroundColor: '#dcfce7', fill: true, yAxisID: 'y' }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { title: { display: true, text: 'Spend vs. Revenue' } },
            scales: { y: { beginAtZero: true } }
        }
    });
    const totals = performanceData.reduce((a, d) => (a.delivered += d.deliveredOrders, a.rto += d.rtoOrders, a.cancelled += d.cancelledOrders, a), { delivered: 0, rto: 0, cancelled: 0 });
    orderStatusChartInstance = new Chart(orderStatusChartCanvas, {
        type: 'doughnut',
        data: {
            labels: ['Delivered', 'RTO', 'Cancelled'],
            datasets: [{ data: [totals.delivered, totals.rto, totals.cancelled], backgroundColor: ['#22c55e', '#ef4444', '#64748b'] }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { title: { display: true, text: 'Order Status Breakdown' } }
        }
    });
}

// === NEW FUNCTION (from adset-performance.js, with fixes) ===
// Calculates and display totals in the summary card
function updateAdsetSummary(data) {
  const card = document.getElementById("adsetSummaryCard");
  if (!card) return;

  if (!data || data.length === 0) {
    card.classList.add("hidden");
    return;
  }

  const totals = data.reduce(
    (acc, item) => {
      acc.spend += parseFloat(item.spend) || 0;
      acc.totalOrders += parseInt(item.totalOrders) || 0;
      acc.delivered += parseInt(item.deliveredOrders) || 0;
      acc.deliveredRevenue += parseFloat(item.deliveredRevenue) || 0;
      acc.rto += parseInt(item.rtoOrders) || 0;
      acc.cancelled += parseInt(item.cancelledOrders) || 0;
      return acc;
    },
    { spend: 0, totalOrders: 0, delivered: 0, deliveredRevenue: 0, rto: 0, cancelled: 0 }
  );

  // --- Update Summary KPIs ---
  document.getElementById("totalSpend").textContent = formatCurrency(totals.spend);
  document.getElementById("totalRevenue").textContent = formatCurrency(totals.deliveredRevenue);
  document.getElementById("totalOrders").textContent = formatNumber(totals.totalOrders);
  document.getElementById("totalDelivered").textContent = formatNumber(totals.delivered);
  document.getElementById("totalRTO").textContent = formatNumber(totals.rto);
  document.getElementById("totalCancelled").textContent = formatNumber(totals.cancelled);

  // --- 🧮 Add ROAS (Return on Ad Spend) ---
  const roas = totals.spend > 0 ? (totals.deliveredRevenue / totals.spend) : 0;
  const roasEl = document.getElementById("totalRoas");
  if (roasEl) {
    roasEl.textContent = `${roas.toFixed(2)}x`;
  }

  card.classList.remove("hidden");
}


// === UPDATED FUNCTION ===
// Renders Adset dashboard, now with sorting and summary card
function renderAdsetPerformanceDashboard() {
    
    // Call summary function
    updateAdsetSummary(adsetPerformanceData);
    
    // Sort data if sort key is set
    if (currentSortKey) {
        adsetPerformanceData.sort((a, b) => {
            let valA = a[currentSortKey];
            let valB = b[currentSortKey];

            // Handle 'name' (string) vs other (numeric) keys
            if (currentSortKey === 'name') {
                 return currentSortOrder === "asc"
                   ? String(valA).localeCompare(String(valB))
                   : String(valB).localeCompare(String(valA));
            } else {
                valA = parseFloat(valA) || 0;
                valB = parseFloat(valB) || 0;
                return currentSortOrder === "asc" ? valA - valB : valB - valA;
            }
        });
    }
    
    // Render table body
    adsetPerformanceTableBody.innerHTML = '';
    if (!adsetPerformanceData || adsetPerformanceData.length === 0) {
        adsetPerformanceTableBody.innerHTML = `<tr><td colspan="13" class="p-4 text-center text-slate-500">No ad set data found for this period.</td></tr>`;
        return;
    }
    
    adsetPerformanceData.forEach(adset => {
        const t = adset.totalOrders || 0;

        // RTO% = (RTO + Cancelled) / (Delivered + RTO + Cancelled)
        const denomAdset = (adset.deliveredOrders || 0) + (adset.rtoOrders || 0) + (adset.cancelledOrders || 0);
        const o = denomAdset > 0 ? ((adset.rtoOrders || 0) + (adset.cancelledOrders || 0)) / denomAdset : 0;
        adset.rtoPercent = o; // Assign for sorting

        const spend = adset.spend || 0;
        const costPerOrder = (spend > 0 && t > 0) ? (spend / t) : 0;
        adset.cpo = costPerOrder; // Assign for sorting
        
        const r = spend > 0 ? (adset.deliveredRevenue || 0) / spend : 0;
        adset.roas = r; // Assign for sorting

        let adsetRow = `
          <tr class="border-b border-slate-200 bg-slate-50 cursor-pointer" data-adset-id="${adset.id}">
            <td class="py-3 px-4 font-bold text-sm text-slate-800 text-left">${adset.name}</td>
            <td class="py-3 px-4 text-sm text-slate-500 text-left">${(adset.terms || []).length} terms</td>
            <td class="py-3 px-4 text-right font-bold">${formatCurrency(spend)}</td>
            <td class="py-3 px-4 text-right font-bold">${formatNumber(t)}</td>
            <td class="py-3 px-4 text-right font-bold text-green-600">${formatNumber(adset.deliveredOrders)}</td>
            <td class="py-3 px-4 text-right font-bold">${formatCurrency(adset.deliveredRevenue)}</td>
            <td class="py-3 px-4 text-right font-bold text-red-600">${formatNumber(adset.rtoOrders)}</td>
            <td class="py-3 px-4 text-right font-bold text-slate-500">${formatNumber(adset.cancelledOrders)}</td>
            <td class="py-3 px-4 text-right font-bold text-blue-600">${formatNumber(adset.inTransitOrders || 0)}</td>
            <td class="py-3 px-4 text-right font-bold text-yellow-600">${formatNumber(adset.processingOrders || 0)}</td>
            <td class="py-3 px-4 text-right font-bold text-red-600">${formatPercent(o)}</td>
            <td class="py-3 px-4 text-right font-bold">${formatCurrency(costPerOrder)}</td>
            <td class="py-3 px-4 text-right font-bold">${r.toFixed(2)}x</td>
          </tr>`;

        (adset.terms || []).forEach(term => {
            const tTerm = term.totalOrders || 0;
            const denomTerm = (term.deliveredOrders || 0) + (term.rtoOrders || 0) + (term.cancelledOrders || 0);
            const oTerm = denomTerm > 0 ? ((term.rtoOrders || 0) + (term.cancelledOrders || 0)) / denomTerm : 0;
            const spendTerm = term.spend || 0;
            const costPerOrderTerm = (spendTerm > 0 && tTerm > 0) ? (spendTerm / tTerm) : 0;
            const rTerm = spendTerm > 0 ? (term.deliveredRevenue || 0) / spendTerm : 0;

            adsetRow += `
              <tr class="adset-term-row hidden border-b border-slate-100" data-parent-adset-id="${adset.id}">
                <td class="py-2 px-8 text-sm text-slate-600 text-left" colspan="2">${term.name || term.id}</td>
                <td class="py-2 px-4 text-right text-sm">${formatCurrency(spendTerm)}</td>
                <td class="py-2 px-4 text-right text-sm">${formatNumber(tTerm)}</td>
                <td class="py-2 px-4 text-right text-sm text-green-600">${formatNumber(term.deliveredOrders)}</td>
                <td class="py-2 px-4 text-right text-sm">${formatCurrency(term.deliveredRevenue)}</td>
                <td class="py-2 px-4 text-right text-sm text-red-600">${formatNumber(term.rtoOrders)}</td>
                <td class="py-2 px-4 text-right text-sm text-slate-500">${formatNumber(term.cancelledOrders)}</td>
                <td class="py-2 px-4 text-right text-sm text-blue-600">${formatNumber(term.inTransitOrders || 0)}</td>
                <td class="py-2 px-4 text-right text-sm text-yellow-600">${formatNumber(term.processingOrders || 0)}</td>
                <td class="py-2 px-4 text-right text-sm text-red-600">${formatPercent(oTerm)}</td>
                <td class="py-2 px-4 text-right text-sm">${formatCurrency(costPerOrderTerm)}</td>
                <td class="py-2 px-4 text-right text-sm">${rTerm.toFixed(2)}x</td>
              </tr>`;
        });

        adsetPerformanceTableBody.innerHTML += adsetRow;
    });

    // Add click listeners for expandable rows
    adsetPerformanceTableBody.querySelectorAll('tr[data-adset-id]').forEach(row => {
        row.addEventListener('click', () => {
            const adsetId = row.dataset.adsetId;
            document.querySelectorAll(`tr[data-parent-adset-id="${adsetId}"]`).forEach(termRow => {
                termRow.classList.toggle('hidden');
            });
        });
    });
}


// ... (rest of your existing functions: renderAllDashboard, renderPlatformFilters, etc.)
function renderAllDashboard(){const[s,e]=calculateDateRange(activeDatePreset,startDateFilterEl.value,endDateFilterEl.value);let o=[...allOrders];if(s&&e){o=o.filter(t=>{const d=new Date(t.date);return d>=s&&d<=e})}if(activePlatformFilter!=='All')o=o.filter(t=>t.platform===activePlatformFilter);if(activeStatusFilter!=='All')o=o.filter(t=>t.status===activeStatusFilter);const t=[...o].sort((a,b)=>new Date(b.date)-new Date(a.date));renderPlatformFilters();renderOrders(t);updateDashboardKpis(o)}
function renderPlatformFilters(){platformFiltersEl.innerHTML=['All','Amazon','Shopify'].map(p=>`<button data-filter="${p}" class="filter-btn px-3 py-1 text-sm rounded-md ${activePlatformFilter===p?'active':''}">${p}</button>`).join('');platformFiltersEl.querySelectorAll('.filter-btn').forEach(b=>{b.addEventListener('click',()=>{activePlatformFilter=b.dataset.filter;renderAllDashboard()})})}
function renderInsightsPlatformFilters(){insightsPlatformFiltersEl.innerHTML=['All','Amazon','Shopify'].map(p=>`<button data-filter="${p}" class="filter-btn px-3 py-1 text-sm rounded-md ${insightsPlatformFilter===p?'active':''}">${p}</button>`).join('');insightsPlatformFiltersEl.querySelectorAll('.filter-btn').forEach(b=>{b.addEventListener('click',()=>{insightsPlatformFilter=b.dataset.filter;renderAllInsights()})})}
function renderOrders(o){ordersListEl.innerHTML='';if(o.length===0){ordersListEl.innerHTML=`<tr><td colspan="6" class="p-4 text-center text-slate-500">No orders found.</td></tr>`;return}
o.forEach(order=>{
    const displayName = (order.name === 'N/A' && order.buyerName) ? order.buyerName : order.name;
    const r=document.createElement('tr');
    r.className=`order-row border-b border-slate-100 cursor-pointer`;
    r.dataset.orderId=order.id;
    r.innerHTML=`<td class="p-4"><img src="${platformLogos[order.platform]||''}" class="w-6 h-6" alt="${order.platform}"></td><td class="p-4 text-slate-600 text-sm">${order.date}</td><td class="p-4 font-semibold text-slate-700">${order.id}</td><td class="p-4 font-medium">${displayName}</td><td class="p-4">${formatCurrency(order.total)}</td><td class="p-4"><span class="px-2 py-1 text-xs font-semibold rounded-full ${getStatusBadge(order.status)}">${order.status}</span></td>`;
    r.addEventListener('click',()=>openOrderModal(order.id));
    ordersListEl.appendChild(r)
})}
function openOrderModal(o){
    const order=allOrders.find(t=>t.id===o);
    if(order){
        selectedOrderId=order.id;
        renderOrderDetails(order);
        orderModal.classList.remove('modal-hidden');
        orderModal.classList.add('modal-visible');
    }
}
function closeOrderModal(){orderModal.classList.add('modal-hidden');orderModal.classList.remove('modal-visible')}
function renderAllInsights(){const[s,e]=calculateDateRange(insightsDatePreset,insightsStartDateFilterEl.value,insightsEndDateFilterEl.value);let o=[...allOrders];if(s&&e){o=o.filter(t=>{const d=new Date(t.date);return d>=s&&d<=e})}if(insightsPlatformFilter!=='All'){o=o.filter(t=>t.platform===insightsPlatformFilter)}
renderInsightsPlatformFilters();const t=calculateComparisonMetrics(o,allOrders,insightsDatePreset,s,e);updateInsightsKpis(o,t);renderInsightCharts(o,s,e)}
function calculateDateRange(p,s,e){const n=new Date();const t=new Date(Date.UTC(n.getUTCFullYear(),n.getUTCMonth(),n.getUTCDate()));let a,d;switch(p){case'today':a=new Date(t);d=new Date(t);break;case'yesterday':a=new Date(t);a.setUTCDate(t.getUTCDate()-1);d=new Date(a);break;case'last_7_days':a=new Date(t);a.setUTCDate(t.getUTCDate()-6);d=new Date(t);break;case'mtd':a=new Date(Date.UTC(t.getUTCFullYear(),t.getUTCMonth(),1));d=new Date(t);break;case'last_month':const y=t.getUTCFullYear();const m=t.getUTCMonth();a=new Date(Date.UTC(y,m-1,1));d=new Date(Date.UTC(y,m,0));break;case'custom':if(!s)return[null,null];const[i,l,c]=s.split('-').map(Number);a=new Date(Date.UTC(i,l-1,c));if(e){const[u,f,h]=e.split('-').map(Number);d=new Date(Date.UTC(u,f-1,h))}else{d=new Date(a)}
break;default:return[null,null]}
d.setUTCHours(23,59,59,999);return[a,d]}
function calculateComparisonMetrics(c,a,p,s,e){let t,d,l='';if(!s||!e)return{periodLabel:'',revenueTrend:'',ordersTrend:''};const o=insightsPlatformFilter==='All'?a:a.filter(r=>r.platform===insightsPlatformFilter);switch(p){case'last_7_days':t=new Date(s);t.setDate(s.getDate()-7);d=new Date(e);d.setDate(e.getDate()-7);l='vs Previous Week';break;case'mtd':case'last_month':t=new Date(s);t.setMonth(s.getMonth()-1);d=new Date(t.getFullYear(),t.getMonth()+1,0);l='vs Previous Month';break;default:return{periodLabel:'',revenueTrend:'',ordersTrend:''}}
d.setHours(23,59,59,999);const r=o.filter(i=>{const n=new Date(i.date);return n>=t&&n<=d});const u=c.filter(i=>i.status!=='Cancelled').reduce((n,i)=>n+i.total,0);const f=r.filter(i=>i.status!=='Cancelled').reduce((n,i)=>n+i.total,0);const h=(n,i)=>{if(i===0)return n>0?'+100%':'+0%';const v=((n-i)/i)*100;return`${v>=0?'+':''}${v.toFixed(1)}%`};return{periodLabel:l,revenueTrend:h(u,f),ordersTrend:h(c.length,r.length)}}
function updateDashboardKpis(o){const k={new:0,processing:0,shipped:0,cancelled:0};o.forEach(s=>{if(s.status==='New')k.new++;else if(s.status==='Processing')k.processing++;else if(s.status==='Shipped')k.shipped++;else if(s.status==='Cancelled')k.cancelled++});const renderKpi=(e,t,v,i)=>{e.innerHTML=`<div class="flex items-center">${i}<p class="text-sm font-medium text-slate-500 ml-2">${t}</p></div><p class="text-3xl font-bold text-slate-800 mt-2">${v}</p>`};renderKpi(dashboardKpiElements.newOrders,'New Orders',k.new,`<svg class="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>`);renderKpi(dashboardKpiElements.processing,'Processing',k.processing,`<svg class="w-6 h-6 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>`);renderKpi(dashboardKpiElements.shipped,'Shipped',k.shipped,`<svg class="w-6 h-6 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17H6V6h11v4l4 4v2h-3zM6 6l6-4l6 4"></path></svg>`);renderKpi(dashboardKpiElements.cancelled,'Cancelled',k.cancelled,`<svg class="w-6 h-6 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"></path></svg>`)}
function updateInsightsKpis(o,c){const a=o.filter(s=>s.status!=='Cancelled');const t=a.reduce((s,r)=>s+r.total,0);const v=a.length>0?t/a.length:0;const l=o.length;const n=o.filter(s=>s.status==='New').length;const p=o.filter(s=>s.status==='Shipped').length;const r=0;const d=o.filter(s=>s.status==='Cancelled').length;const renderKpi=(e,i,u,f,h,m)=>{const g=h&&h.startsWith('+')?'text-green-500':'text-red-500';e.innerHTML=`<div class="flex items-center">${f}<p class="text-xs font-medium text-slate-500 ml-2">${i}</p></div><p class="text-2xl font-bold text-slate-800 mt-2">${u}</p>${h?`<p class="text-xs ${g} mt-1">${h} <span class="text-slate-400">${m}</span></p>`:`<p class="text-xs text-slate-400 mt-1">&nbsp;</p>`}`};renderKpi(insightsKpiElements.revenue.el,'Total Revenue',formatCurrency(t),`<svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v.01"></path></svg>`,c.revenueTrend,c.periodLabel);renderKpi(insightsKpiElements.avgValue.el,'Avg. Value',formatCurrency(v),`<svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 6l3 6h10a2 2 0 001.79-1.11L21 8M6 18h12a2 2 0 002-2v-5a2 2 0 00-2-2H6a2 2 0 00-2 2v5a2 2 0 002 2z"></path></svg>`,'','');renderKpi(insightsKpiElements.allOrders.el,'All Orders',l,`<svg class="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z"></path></svg>`,c.ordersTrend,c.periodLabel);renderKpi(insightsKpiElements.new.el,'New Orders',n,`<svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z"></path></svg>`,'','');renderKpi(insightsKpiElements.shipped.el,'Shipped',p,`<svg class="w-5 h-5 text-indigo-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path d="M9 17a2 2 0 11-4 0 2 2 0 014 0zM19 17a2 2 0 11-4 0 2 2 0 014 0z"></path><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 17H6V6h11v4l4 4v2h-3zM6 6l6-4l6 4"></path></svg>`,'','');renderKpi(insightsKpiElements.rto.el,'RTO',r,`<svg class="w-5 h-5 text-orange-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 9l-5 5-5-5"></path></svg>`,'','');renderKpi(insightsKpiElements.cancelled.el,'Cancelled',d,`<svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636"></path></svg>`,'','')}
function renderInsightCharts(o,s,e){if(revenueChartInstance)revenueChartInstance.destroy();if(platformChartInstance)platformChartInstance.destroy();if(paymentChartInstance)paymentChartInstance.destroy();const d={};if(s&&e){let c=new Date(s);while(c<=e){d[c.toISOString().split('T')[0]]=0;c.setDate(c.getDate()+1)}}
o.forEach(r=>{if(r.status!=='Cancelled'){const i=new Date(r.date).toISOString().split('T')[0];if(d[i]!==undefined)d[i]+=r.total}});revenueChartInstance=new Chart(revenueChartCanvas,{type:'line',data:{labels:Object.keys(d).map(l=>new Date(l).toLocaleDateString('en-US',{timeZone:'UTC',month:'short',day:'numeric'})),datasets:[{label:'Revenue',data:Object.values(d),borderColor:'rgb(79, 70, 229)',backgroundColor:'rgba(79, 70, 229, 0.1)',fill:true,tension:0.1}]},options:{responsive:true,maintainAspectRatio:false,plugins:{title:{display:true,text:'Revenue Over Time'}}}});const p={Shopify:0,Amazon:0};o.forEach(r=>{if(r.status!=='Cancelled'&&p[r.platform]!==undefined)p[r.platform]+=r.total});platformChartInstance=new Chart(platformChartCanvas,{type:'doughnut',data:{labels:Object.keys(p),datasets:[{data:Object.values(p),backgroundColor:['#96bf48','#ff9900']}]},options:{responsive:true,maintainAspectRatio:false,plugins:{title:{display:true,text:'Revenue by Platform'}}}});const m={Prepaid:0,COD:0};o.forEach(r=>{if(r.paymentMethod){const i=r.paymentMethod.toLowerCase();if(i.includes("cod")||i.includes("cash")){m.COD++}else{m.Prepaid++}}});paymentChartInstance=new Chart(paymentChartCanvas,{type:'doughnut',data:{labels:Object.keys(m),datasets:[{data:Object.values(m),backgroundColor:['#10b981','#f59e0b']}]},options:{responsive:true,maintainAspectRatio:false,plugins:{title:{display:true,text:'Prepaid vs. COD'},tooltip:{callbacks:{label:c=>{const t=c.chart.data.datasets[0].data.reduce((a,b)=>a+b,0);const p=t>0?((c.raw/t)*100).toFixed(1)+'%':'0%';return`${c.label}: ${c.raw} (${p})`}}}}}})}
function renderSettings(){const c=document.getElementById('seller-connections');c.innerHTML=connections.map(e=>`<div class="bg-white p-4 rounded-lg shadow-sm flex items-center justify-between"><div class="flex items-center"><img src="${platformLogos[e.name]}" class="w-10 h-10 mr-4"><div><p class="font-semibold text-lg">${e.name}</p><p class="text-sm text-slate-500">${e.status==='Connected'?e.user:'Click to connect'}</p></div></div><button data-platform="${e.name}" data-action="${e.status==='Connected'?'disconnect':'connect'}" class="connection-btn ${e.status==='Connected'?'font-medium text-sm text-red-600 hover:text-red-800':'font-medium text-sm text-white bg-indigo-600 hover:bg-indigo-700 px-4 py-2 rounded-lg'}">${e.status==='Connected'?'Disconnect':'Connect'}</button></div>`).join('');document.querySelectorAll('.connection-btn').forEach(b=>b.addEventListener('click',e=>handleConnection(e.currentTarget.dataset.platform,e.currentTarget.dataset.action)))}
function handleConnection(p,a){if(a==='connect'){showNotification(`Simulating connection to ${p}...`);setTimeout(()=>{showNotification(`Successfully connected to ${p}.`)},1500)}else if(a==='disconnect'){if(confirm(`Are you sure you want to disconnect from ${p}?`)){showNotification(`Disconnected from ${p}.`)}}}
async function loadInitialData(){try{allOrders=await fetchOrdersFromServer();initializeAllFilters();navigate('orders-dashboard');setInterval(async()=>{if(['orders-dashboard','order-insights'].includes(currentView)){try{allOrders=await fetchOrdersFromServer();if(currentView==='orders-dashboard')renderAllDashboard();else renderAllInsights()}catch(e){console.error("Periodic refresh failed.")}}},120000)}catch(error){}}
function initializeAllFilters(){statusFilterEl.innerHTML=['All Statuses','New','Processing','Shipped','Cancelled'].map(s=>`<option value="${s==='All Statuses'?'All':s}">${s}</option>`).join('');statusFilterEl.value=activeStatusFilter;statusFilterEl.addEventListener('change',e=>{activeStatusFilter=e.target.value;renderAllDashboard()});const d={'today':'Today','yesterday':'Yesterday','last_7_days':'Last 7 Days','mtd':'Month to Date','last_month':'Last Month','custom':'Custom Range...'};initializeDateFilters(insightsDatePresetFilter,insightsCustomDateContainer,insightsStartDateFilterEl,insightsEndDateFilterEl,'insightsDatePreset',renderAllInsights,d);initializeDateFilters(adDatePresetFilter,adCustomDateContainer,adStartDateFilterEl,adEndDateFilterEl,'adPerformanceDatePreset',handleAdPerformanceDateChange,d);initializeDateFilters(adsetDatePresetFilter,adsetCustomDateContainer,adsetStartDateFilterEl,adsetEndDateFilterEl,'adsetDatePreset',handleAdsetDateChange,d);initializeDateFilters(orderDatePresetFilter,customDateContainer,startDateFilterEl,endDateFilterEl,'activeDatePreset',renderAllDashboard,d);renderInsightsPlatformFilters()}
function initializeDateFilters(d,c,s,e,p,h,t){d.innerHTML=Object.entries(t).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');if(p==='insightsDatePreset')d.value=insightsDatePreset;else if(p==='adPerformanceDatePreset')d.value=adPerformanceDatePreset;else if(p==='adsetDatePreset')d.value=adsetDatePreset;else if(p==='activeDatePreset')d.value=activeDatePreset;const dateChange=()=>{const v=d.value;if(p==='insightsDatePreset')insightsDatePreset=v;else if(p==='adPerformanceDatePreset')adPerformanceDatePreset=v;else if(p==='adsetDatePreset')adsetDatePreset=v;else if(p==='activeDatePreset')activeDatePreset=v;c.classList.toggle('hidden',v!=='custom');h()};d.addEventListener('change',dateChange);s.addEventListener('change',h);e.addEventListener('change',h)}
async function handlePdfDownload(){const[s,e]=calculateDateRange(adsetDatePreset,adsetStartDateFilterEl.value,adsetEndDateFilterEl.value);if(!adsetPerformanceData||adsetPerformanceData.length===0){showNotification("No data available to download.",true);return}
if(!s||!e){showNotification("Please select a valid date range.",true);return}
const since=s.toISOString().split('T')[0];const until=e.toISOString().split('T')[0];showNotification("Generating PDF report...");try{const blob=await fetchApiData(`/download-dashboard-pdf?since=${since}&until=${until}`,"Failed to generate PDF",{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(adsetPerformanceData)});const url=window.URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`adset_report_${since}_to_${until}.pdf`;document.body.appendChild(a);a.click();a.remove();window.URL.revokeObjectURL(url);showNotification("PDF download started successfully!")}catch(err){}}

async function handleExcelDownload() {
    const [startDate, endDate] = calculateDateRange(adsetDatePreset, adsetStartDateFilterEl.value, adsetEndDateFilterEl.value);
    if (!startDate || !endDate) {
        showNotification("Please select a valid date range.", true);
        return;
    }
    const since = startDate.toISOString().split('T')[0];
    const until = endDate.toISOString().split('T')[0];
    showNotification("Generating detailed Excel report...");
    
    // const endpoint = `/download-excel-report?since=${since}&until=${until}`; // This was the old endpoint
    // Using the adset endpoint from your HTML button ID
    const dateFilterType = adsetDateFilterTypeEl ? adsetDateFilterTypeEl.value : 'order_date';
    const endpoint = `/get-adset-performance?since=${since}&until=${until}&date_filter_type=${dateFilterType}&format=excel`;

    try {
        // We assume the adset endpoint (or a similar one) can return excel
        // If your backend is different, you might need a different endpoint.
        // For this example, let's assume '/download-excel-report' is correct
        const excelEndpoint = `/download-excel-report?since=${since}&until=${until}&date_filter_type=${dateFilterType}`;

        const blob = await fetchApiData(excelEndpoint, "Failed to generate Excel report");
        const downloadUrl = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = downloadUrl;
        a.download = `detailed_report_${since}_to_${until}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(downloadUrl);
    } catch(e) { /* Handled by fetchApiData */ }
}

document.getElementById('nav-reports')?.addEventListener('click', (e) => {
  e.preventDefault();
  ['orders-dashboard-view','order-insights-view','ad-performance-view','adset-breakdown-view','reports-view','settings-view']
    .forEach(id => document.getElementById(id)?.classList.add('view-hidden'));
  document.getElementById('reports-view')?.classList.remove('view-hidden');
  document.querySelectorAll('.sidebar-link').forEach(el => el.classList.remove('active'));
  document.getElementById('nav-reports')?.classList.add('active');
});

document.getElementById('btn-download-amazon-report')?.addEventListener('click', async () => {
    const startDate = document.getElementById('amazon-report-start-date').value;
    const endDate = document.getElementById('amazon-report-end-date').value;
    
    if (!startDate || !endDate) {
        showNotification('Please select both start and end dates', true);
        return;
    }
    
    showNotification('Generating Amazon report...');
    
    try {
        const blob = await fetchApiData(`/download-amazon-sales-report?start_date=${startDate}&end_date=${endDate}`, 'Failed to generate Amazon report');
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `amazon_mtr_report_${startDate}_to_${endDate}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showNotification('Amazon report downloaded successfully!');
    } catch (error) {
        // Error already handled by fetchApiData
    }
});

document.addEventListener('DOMContentLoaded', () => {
    loginView = document.getElementById('login-view');
    appView = document.getElementById('app');
    logoutBtn = document.getElementById('logout-btn');
    loginBtn = document.getElementById('login-btn');
    loginEmailEl = document.getElementById('login-email');
    loginPasswordEl = document.getElementById('login-password');
    notificationEl = document.getElementById('notification');
    notificationMessageEl = document.getElementById('notification-message');
    navOrdersDashboard = document.getElementById('nav-orders-dashboard');
    navOrderInsights = document.getElementById('nav-order-insights');
    navAdPerformance = document.getElementById('nav-ad-performance');
    navAdsetBreakdown = document.getElementById('nav-adset-breakdown');
    navSettings = document.getElementById('nav-settings');
    ordersDashboardView = document.getElementById('orders-dashboard-view');
    orderInsightsView = document.getElementById('order-insights-view');
    adPerformanceView = document.getElementById('ad-performance-view');
    adsetBreakdownView = document.getElementById('adset-breakdown-view');
    settingsView = document.getElementById('settings-view');
    ordersListEl = document.getElementById('orders-list');
    statusFilterEl = document.getElementById('status-filter');
    orderDatePresetFilter = document.getElementById('order-date-preset-filter');
    customDateContainer = document.getElementById('custom-date-container');
    startDateFilterEl = document.getElementById('start-date-filter');
    endDateFilterEl = document.getElementById('end-date-filter');
    platformFiltersEl = document.getElementById('platform-filters');
    dashboardKpiElements = { newOrders: document.getElementById('kpi-dashboard-new'), processing: document.getElementById('kpi-dashboard-processing'), shipped: document.getElementById('kpi-dashboard-shipped'), cancelled: document.getElementById('kpi-dashboard-cancelled') };
    insightsKpiElements = { revenue: { el: document.getElementById('kpi-insights-revenue') }, avgValue: { el: document.getElementById('kpi-insights-avg-value') }, allOrders: { el: document.getElementById('kpi-insights-all-orders') }, new: { el: document.getElementById('kpi-insights-new') }, shipped: { el: document.getElementById('kpi-insights-shipped') }, rto: { el: document.getElementById('kpi-insights-rto') }, cancelled: { el: document.getElementById('kpi-insights-cancelled') }};
    revenueChartCanvas = document.getElementById('revenue-chart');
    platformChartCanvas = document.getElementById('platform-chart');
    paymentChartCanvas = document.getElementById('payment-chart');
    insightsDatePresetFilter = document.getElementById('insights-date-preset-filter');
    insightsCustomDateContainer = document.getElementById('insights-custom-date-container');
    insightsStartDateFilterEl = document.getElementById('insights-start-date-filter');
    insightsEndDateFilterEl = document.getElementById('insights-end-date-filter');
    insightsPlatformFiltersEl = document.getElementById('insights-platform-filters');
    orderModal = document.getElementById('order-modal');
    modalBackdrop = document.getElementById('modal-backdrop');
    modalContent = document.getElementById('modal-content');
    modalCloseBtn = document.getElementById('modal-close-btn');
    adDatePresetFilter = document.getElementById('ad-date-preset-filter');
    adCustomDateContainer = document.getElementById('ad-custom-date-container');
    adStartDateFilterEl = document.getElementById('ad-start-date-filter');
    adEndDateFilterEl = document.getElementById('ad-end-date-filter');
    performanceTableBody = document.getElementById('performance-table-body');
    adKpiElements = { totalSpend: document.getElementById('kpi-total-spend'), totalRevenue: document.getElementById('kpi-total-revenue'), roas: document.getElementById('kpi-roas'), delivered: document.getElementById('kpi-delivered'), rto: document.getElementById('kpi-rto'), cancelled: document.getElementById('kpi-cancelled') };
    
    spendRevenueChartCanvas = document.getElementById('spend-revenue-chart');
    orderStatusChartCanvas = document.getElementById('order-status-chart');
    adsetDatePresetFilter = document.getElementById('adset-date-preset-filter');
    adsetCustomDateContainer = document.getElementById('adset-custom-date-container');
    adsetStartDateFilterEl = document.getElementById('adset-start-date-filter');
    adsetEndDateFilterEl = document.getElementById('adset-end-date-filter');
    adsetPerformanceTableBody = document.getElementById('adset-performance-table-body');
    
    // Updated to use the new IDs from your latest HTML
    downloadPdfBtn = document.getElementById('download-adset-pdf');
    downloadExcelBtn = document.getElementById('download-adset-excel');
    
    adsetDateFilterTypeEl = document.getElementById('adset-date-filter-type');

    loginBtn?.addEventListener('click', handleLogin);
    loginEmailEl?.addEventListener('keypress', e => { if (e.key === 'Enter') handleLogin(); });
    loginPasswordEl?.addEventListener('keypress', e => { if (e.key === 'Enter') handleLogin(); });
    logoutBtn?.addEventListener('click', logout);
    navOrdersDashboard?.addEventListener('click', (e) => { e.preventDefault(); navigate('orders-dashboard'); });
    navOrderInsights?.addEventListener('click', (e) => { e.preventDefault(); navigate('order-insights'); });
    navAdPerformance?.addEventListener('click', (e) => { e.preventDefault(); navigate('ad-performance'); });
    navAdsetBreakdown?.addEventListener('click', (e) => { e.preventDefault(); navigate('adset-breakdown'); });
    navSettings?.addEventListener('click', (e) => { e.preventDefault(); navigate('settings'); });
    modalCloseBtn?.addEventListener('click', closeOrderModal);
    modalBackdrop?.addEventListener('click', closeOrderModal);
    
    // Listeners for the download buttons
    downloadPdfBtn?.addEventListener('click', handlePdfDownload);
    downloadExcelBtn?.addEventListener('click', handleExcelDownload);
    
    adsetDateFilterTypeEl?.addEventListener('change', handleAdsetDateChange);

    // === NEW: Add sort listeners on load ===
    document.querySelectorAll("#adsetPerformanceTable th.sortable").forEach(th => {
        // Store original text
        th.dataset.originalText = th.textContent.replace(/[▲▼⬍]/g, "").trim();
        
        th.onclick = () => {
            const key = th.dataset.key;
            if (!key) return;

            if (currentSortKey === key) {
                currentSortOrder = currentSortOrder === "asc" ? "desc" : "asc";
            } else {
                currentSortKey = key;
                currentSortOrder = "asc";
            }

            // Visually update header arrows
            document.querySelectorAll("#adsetPerformanceTable th.sortable").forEach(h => {
                h.textContent = `${h.dataset.originalText} ⬍`;
            });
            th.textContent = `${th.dataset.originalText} ${currentSortOrder === "asc" ? "▲" : "▼"}`;

            // Re-render the table with the new sort
            renderAdsetPerformanceDashboard();
        };
    });
    // ======================================

    const savedToken = localStorage.getItem('authToken');
    if (savedToken) {
        authToken = savedToken;
        showApp();
    } else {
        showLogin();
        prefillLoginDetails();
    }
});