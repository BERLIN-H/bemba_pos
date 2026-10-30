const cart = document.querySelector('#cart');
const cartItems = [];
const sendKitchenButton = document.querySelector('#send-kitchen');
const tableSelect = document.querySelector('#table-select');
const posMessage = document.querySelector('#pos-message');
const cartSummary = document.querySelector('#cart-summary');
const saveHoldButton = document.querySelector('#save-hold');
const loadHoldButton = document.querySelector('#load-hold');
const transferTableSelect = document.querySelector('#transfer-table-select');
const transferTableButton = document.querySelector('#transfer-table');
const menuSearch = document.querySelector('#menu-search');
const categoryFilters = document.querySelectorAll('.pos-menu .filter-pill');
const inventorySearch = document.querySelector('.inventory-search');

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
  return '';
}

function money(value) {
  return Number(value).toLocaleString('es-CO', {
    style: 'currency',
    currency: 'COP',
    minimumFractionDigits: 0,
  });
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Convierte el JSON de error de la API en un texto legible (ya escapado para usar con innerHTML).
function readableError(error, fallback) {
  try {
    const data = JSON.parse(error.message);
    const parts = [];
    const collect = (value) => {
      if (Array.isArray(value)) value.forEach(collect);
      else if (value && typeof value === 'object') Object.values(value).forEach(collect);
      else if (value) parts.push(String(value));
    };
    collect(data);
    return parts.length ? escapeHtml(parts.join(' ')) : fallback;
  } catch (_) {
    return fallback;
  }
}

function setPosMessage(message, type = 'muted') {
  if (!posMessage) return;
  posMessage.className = `small mt-3 text-${type}`;
  posMessage.innerHTML = message;
}

function updateCartSummary() {
  if (!cartSummary) return;
  if (!cartItems.length) {
    cartSummary.innerHTML = '';
    return;
  }

  const total = cartItems.reduce((sum, item) => sum + item.price * item.quantity, 0);
  cartSummary.innerHTML = `
    <div class="cart-summary-row">
      <span>${cartItems.length} artículo(s) · Total</span>
      <strong>${money(total)}</strong>
    </div>
    <button id="clear-cart" type="button" class="btn btn-sm btn-outline-secondary">Limpiar ticket</button>
  `;

  const clearButton = document.querySelector('#clear-cart');
  if (clearButton) {
    clearButton.addEventListener('click', () => {
      cartItems.length = 0;
      renderCart();
      setPosMessage('Ticket limpio. Agrega productos para crear un nuevo pedido.', 'muted');
    });
  }
}

function renderCart() {
  if (!cart) return;

  if (!cartItems.length) {
    cart.className = 'cart-empty';
    cart.innerHTML = 'Selecciona productos para crear el pedido.';
    updateCartSummary();
    return;
  }

  cart.className = 'cart-list';
  cart.innerHTML = cartItems
    .map((item) => `
      <div class="cart-row" data-id="${item.id}">
        <div>
          <strong>${escapeHtml(item.name)}</strong>
          <small>${money(item.price)} c/u</small>
        </div>
        <div class="cart-controls">
          <button type="button" class="btn btn-sm btn-outline-secondary" data-action="decrease" data-id="${item.id}">-</button>
          <span>${item.quantity}</span>
          <button type="button" class="btn btn-sm btn-outline-secondary" data-action="increase" data-id="${item.id}">+</button>
          <button type="button" class="btn btn-sm btn-link text-danger" data-action="remove" data-id="${item.id}">Quitar</button>
        </div>
      </div>
    `)
    .join('');

  updateCartSummary();
}

function addCartItem(button) {
  const id = Number(button.dataset.id);
  const name = button.querySelector('strong')?.textContent || 'Producto';
  const price = Number(button.dataset.price.replace(',', '.'));
  const existingItem = cartItems.find((item) => item.id === id);

  if (existingItem) {
    existingItem.quantity += 1;
  } else {
    cartItems.push({ id, name, price, quantity: 1 });
  }
  renderCart();
}

document.querySelectorAll('.menu-item').forEach((button) => {
  button.addEventListener('click', () => addCartItem(button));
});

if (cart) {
  cart.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-action]');
    if (!button) return;
    const action = button.dataset.action;
    const id = Number(button.dataset.id);
    const item = cartItems.find((entry) => entry.id === id);
    if (!item) return;

    if (action === 'increase') {
      item.quantity += 1;
    } else if (action === 'decrease') {
      item.quantity = Math.max(item.quantity - 1, 1);
    } else if (action === 'remove') {
      const index = cartItems.indexOf(item);
      if (index > -1) cartItems.splice(index, 1);
    }

    renderCart();
  });
}

if (saveHoldButton) {
  saveHoldButton.addEventListener('click', () => {
    if (!cartItems.length) {
      setPosMessage('No hay productos para guardar.', 'danger');
      return;
    }
    localStorage.setItem('bemba_pos_hold', JSON.stringify({ table: Number(tableSelect.value), items: cartItems }));
    setPosMessage('Pedido guardado en espera. Pulsa Cargar pedido guardado para restaurarlo.', 'success');
  });
}

if (loadHoldButton) {
  loadHoldButton.addEventListener('click', () => {
    const stored = localStorage.getItem('bemba_pos_hold');
    if (!stored) {
      setPosMessage('No se encontró un pedido guardado.', 'danger');
      return;
    }

    const hold = JSON.parse(stored);
    if (hold.table) tableSelect.value = hold.table;
    cartItems.length = 0;
    hold.items?.forEach((item) => cartItems.push(item));
    renderCart();
    setPosMessage('Pedido restaurado. Revisa la lista antes de enviar a cocina.', 'success');
  });
}

if (sendKitchenButton) {
  sendKitchenButton.addEventListener('click', async () => {
    if (!cartItems.length) {
      setPosMessage('Agrega al menos un producto al ticket.', 'danger');
      return;
    }

    sendKitchenButton.disabled = true;
    setPosMessage('Creando pedido y enviando comanda...', 'muted');

    try {
      const orderResponse = await fetch('/api/orders/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({
          table: Number(tableSelect.value),
          items: cartItems.map((item) => ({
            menu_item: item.id,
            quantity: item.quantity,
          })),
        }),
      });

      if (!orderResponse.ok) {
        const error = await orderResponse.json();
        throw new Error(JSON.stringify(error));
      }

      const order = await orderResponse.json();
      const kitchenResponse = await fetch(`/api/orders/${order.id}/send_to_kitchen/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
      });

      if (!kitchenResponse.ok) {
        const error = await kitchenResponse.json();
        throw new Error(JSON.stringify(error));
      }

      cartItems.length = 0;
      renderCart();
      setPosMessage(`Pedido #${order.id} enviado a cocina. <a href="/kitchen/">Ver cocina</a> · <a href="/pos/checkout/${order.id}/">Cobrar</a>`, 'success');
    } catch (error) {
      setPosMessage(readableError(error, 'No se pudo enviar el pedido. Revisa la mesa y los productos.'), 'danger');
      console.error(error);
    } finally {
      sendKitchenButton.disabled = false;
    }
  });
}

if (transferTableButton) {
  transferTableButton.addEventListener('click', async () => {
    const orderId = checkoutForm?.dataset.orderId;
    const tableId = Number(transferTableSelect?.value);
    if (!orderId || !tableId) {
      setPosMessage('Selecciona una mesa destino válida.', 'danger');
      return;
    }

    transferTableButton.disabled = true;
    setPosMessage('Transferiendo pedido...', 'muted');

    try {
      const response = await fetch(`/api/orders/${orderId}/`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({ table: tableId }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(JSON.stringify(error));
      }

      setPosMessage('Pedido transferido correctamente. Actualiza para ver la nueva mesa.', 'success');
    } catch (error) {
      setPosMessage(readableError(error, 'No se pudo transferir el pedido. Intenta nuevamente.'), 'danger');
      console.error(error);
    } finally {
      transferTableButton.disabled = false;
    }
  });
}

function initKeyboardShortcuts() {
  document.addEventListener('keydown', (event) => {
    if (event.altKey && event.key.toLowerCase() === 's') {
      event.preventDefault();
      sendKitchenButton?.click();
    }
    if (event.altKey && event.key.toLowerCase() === 'h') {
      event.preventDefault();
      saveHoldButton?.click();
    }
    if (event.key === 'Enter' && document.activeElement === menuSearch) {
      event.preventDefault();
      const firstItem = document.querySelector('.menu-item:not([hidden])');
      firstItem?.click();
    }
  });
}

function initMenuFilters() {
  if (!menuSearch && !categoryFilters.length) return;

  const menuButtons = Array.from(document.querySelectorAll('.menu-item'));

  function updateMenuDisplay() {
    const searchValue = menuSearch?.value.trim().toLowerCase() || '';
    const activeCategory = document.querySelector('.pos-menu .filter-pill.active')?.dataset.filter || 'all';

    menuButtons.forEach((button) => {
      const name = button.querySelector('strong')?.textContent.toLowerCase() || '';
      const category = button.dataset.category;
      const matchesSearch = !searchValue || name.includes(searchValue);
      const matchesCategory = activeCategory === 'all' || category === activeCategory;
      button.hidden = !(matchesSearch && matchesCategory);
    });
  }

  menuSearch?.addEventListener('input', updateMenuDisplay);

  categoryFilters.forEach((pill) => {
    pill.addEventListener('click', () => {
      categoryFilters.forEach((btn) => btn.classList.remove('active'));
      pill.classList.add('active');
      updateMenuDisplay();
    });
  });
}

function initInventorySearch() {
  if (!inventorySearch) return;
  const searchableItems = Array.from(document.querySelectorAll('.inventory-search-item'));
  const status = document.querySelector('.inventory-search-status');
  const emptyState = document.querySelector('.inventory-empty-search');

  function normalizeText(value) {
    return (value || '')
      .toString()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .trim();
  }

  searchableItems.forEach((item) => {
    if (!item.dataset.inventoryDisplay) {
      item.dataset.inventoryDisplay = getComputedStyle(item).display === 'none'
        ? ''
        : getComputedStyle(item).display;
    }
  });

  function setItemVisible(item, visible) {
    if (visible) {
      item.style.display = item.dataset.inventoryDisplay || '';
      return;
    }
    item.style.display = 'none';
  }

  inventorySearch.addEventListener('input', () => {
    const query = normalizeText(inventorySearch.value);
    let visibleCount = 0;

    searchableItems.forEach((item) => {
      const text = normalizeText(item.textContent);
      const visible = !query || text.includes(query);
      setItemVisible(item, visible);
      if (visible && query) visibleCount += 1;
    });

    if (status) {
      status.textContent = query
        ? `${visibleCount} resultado(s) encontrado(s)`
        : '';
    }
    if (emptyState) {
      emptyState.hidden = !query || visibleCount > 0;
    }
  });
}

function initKitchenActions() {
  const grid = document.querySelector('.kitchen-grid');
  const filters = document.querySelectorAll('.filter-pill');

  if (grid) {
    grid.addEventListener('click', async (event) => {
      const button = event.target.closest('.ticket-action-btn');
      if (!button) return;

      const orderId = button.dataset.orderId;
      const status = button.dataset.status;
      button.disabled = true;
      button.textContent = 'Actualizando...';

      try {
        const response = await fetch(`/api/orders/${orderId}/`, {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken'),
          },
          body: JSON.stringify({ status }),
        });
        if (!response.ok) throw new Error('No se pudo actualizar el estado.');
        window.location.reload();
      } catch (error) {
        console.error(error);
        button.disabled = false;
        button.textContent = status === 'ready' ? 'Marcar listo' : 'Marcar preparando';
      }
    });
  }

  filters.forEach((pill) => {
    pill.addEventListener('click', () => {
      filters.forEach((btn) => btn.classList.remove('active'));
      pill.classList.add('active');
      const filter = pill.dataset.filter;
      document.querySelectorAll('.ticket-card').forEach((card) => {
        card.style.display = filter === 'all' || card.dataset.status === filter ? 'grid' : 'none';
      });
    });
  });
}

function initDashboardCharts() {
  const dataNode = document.querySelector('#dashboard-data');
  if (!dataNode || typeof Chart === 'undefined') return;

  const dashboardData = JSON.parse(dataNode.textContent || '{}');
  const palette = {
    blue: '#4389e8',
    orange: '#f97345',
    rose: '#ec4899',
    teal: '#0f766e',
    amber: '#f59e0b',
    slate: '#475569',
  };

  const moneyTick = (value) => Number(value || 0).toLocaleString('es-CO', {
    style: 'currency',
    currency: 'COP',
    maximumFractionDigits: 0,
  });

  function hasValues(values) {
    return Array.isArray(values) && values.some((value) => Number(value) > 0);
  }

  function makeChart(canvasId, config) {
    const canvas = document.querySelector(`#${canvasId}`);
    if (!canvas) return;
    new Chart(canvas, config);
  }

  makeChart('salesTrendChart', {
    type: 'line',
    data: {
      labels: dashboardData.dailySales?.labels || [],
      datasets: [{
        label: 'Ventas',
        data: dashboardData.dailySales?.values || [],
        borderColor: palette.blue,
        backgroundColor: 'rgba(67, 137, 232, 0.16)',
        fill: true,
        tension: 0.36,
        pointRadius: 4,
        pointBackgroundColor: palette.blue,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (context) => moneyTick(context.raw) } },
      },
      scales: {
        y: { beginAtZero: true, ticks: { callback: moneyTick } },
        x: { grid: { display: false } },
      },
    },
  });

  makeChart('topProductsChart', {
    type: 'bar',
    data: {
      labels: dashboardData.topProducts?.labels || [],
      datasets: [{
        label: 'Unidades',
        data: dashboardData.topProducts?.values || [],
        backgroundColor: palette.orange,
        borderRadius: 10,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { beginAtZero: true },
        y: { grid: { display: false } },
      },
    },
  });

  const donutOptions = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '62%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: { boxWidth: 12, usePointStyle: true },
      },
    },
  };

  function donutData(source, fallbackLabel) {
    const labels = source?.labels || [];
    const values = source?.values || [];
    if (!hasValues(values)) {
      return { labels: [fallbackLabel], values: [1] };
    }
    return { labels, values };
  }

  const payments = donutData(dashboardData.paymentMethods, 'Sin pagos');
  makeChart('paymentMethodsChart', {
    type: 'doughnut',
    data: {
      labels: payments.labels,
      datasets: [{ data: payments.values, backgroundColor: [palette.blue, palette.amber, palette.teal, palette.rose] }],
    },
    options: donutOptions,
  });

  const orders = donutData(dashboardData.orderStatuses, 'Sin pedidos');
  makeChart('orderStatusChart', {
    type: 'doughnut',
    data: {
      labels: orders.labels,
      datasets: [{ data: orders.values, backgroundColor: [palette.orange, palette.blue, palette.teal, palette.amber, palette.rose, palette.slate] }],
    },
    options: donutOptions,
  });

  const tables = donutData(dashboardData.tableStatuses, 'Sin mesas');
  makeChart('tableStatusChart', {
    type: 'doughnut',
    data: {
      labels: tables.labels,
      datasets: [{ data: tables.values, backgroundColor: [palette.teal, palette.orange, palette.blue, palette.slate] }],
    },
    options: donutOptions,
  });
}

const checkoutForm = document.querySelector('#checkout-form');

if (checkoutForm) {
  const amountInput = checkoutForm.querySelector('[name="amount"]');
  const receivedInput = checkoutForm.querySelector('[name="received"]');
  const changeOutput = checkoutForm.querySelector('#payment-change');
  const checkoutMessage = checkoutForm.querySelector('#checkout-message');
  const submitButton = checkoutForm.querySelector('[type="submit"]');

  function updateChange() {
    const amount = Number(amountInput.value || 0);
    const received = Number(receivedInput.value || 0);
    changeOutput.textContent = money(Math.max(received - amount, 0));
  }

  receivedInput.addEventListener('input', updateChange);
  updateChange();

  checkoutForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    submitButton.disabled = true;
    checkoutMessage.className = 'small mt-3 text-muted';
    checkoutMessage.textContent = 'Registrando pago...';

    try {
      const response = await fetch('/api/payments/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': getCookie('csrftoken'),
        },
        body: JSON.stringify({
          order: Number(checkoutForm.dataset.orderId),
          method: checkoutForm.querySelector('[name="method"]').value,
          amount: Number(amountInput.value),
          received: Number(receivedInput.value),
          reference: checkoutForm.querySelector('[name="reference"]').value,
        }),
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(JSON.stringify(error));
      }

      checkoutMessage.className = 'small mt-3 text-success';
      checkoutMessage.textContent = 'Pago registrado correctamente. Abriendo ticket...';
      window.location.href = `/pos/ticket/${checkoutForm.dataset.orderId}/`;
    } catch (error) {
      checkoutMessage.className = 'small mt-3 text-danger';
      checkoutMessage.textContent = 'No se pudo registrar el pago. Verifica los datos.';
      try {
        const detail = [];
        const collect = (value) => {
          if (Array.isArray(value)) value.forEach(collect);
          else if (value && typeof value === 'object') Object.values(value).forEach(collect);
          else if (value) detail.push(String(value));
        };
        collect(JSON.parse(error.message));
        if (detail.length) checkoutMessage.textContent = detail.join(' ');
      } catch (_) { /* se deja el mensaje genérico */ }
      console.error(error);
    } finally {
      submitButton.disabled = false;
    }
  });
}

renderCart();
initMenuFilters();
initInventorySearch();
initKeyboardShortcuts();
initKitchenActions();
initDashboardCharts();
