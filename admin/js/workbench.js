checkAuth();

const { createApp, ref, computed, onMounted } = Vue;
const PRINT_QUEUE_KEY = "sydroo_order_print_queue_v1";
const PRINT_PAGE_VERSION = "20260428-0235";
const NEW_CATEGORY_VALUE = "__new_category__";

const getVantApi = () => window.vant || {};

const showToast = (message) => {
  const text = typeof message === "string" ? message : message?.message || String(message || "");
  const vantApi = getVantApi();
  if (typeof vantApi.showToast === "function") return vantApi.showToast(text);
  if (typeof vantApi.Toast === "function") return vantApi.Toast(text);
  window.alert(text);
  console.info(text);
  return null;
};

const showConfirmDialog = (options = {}) => {
  const vantApi = getVantApi();
  if (typeof vantApi.showConfirmDialog === "function") return vantApi.showConfirmDialog(options);
  if (typeof vantApi.Dialog?.confirm === "function") return vantApi.Dialog.confirm(options);
  const text = [options.title, options.message].filter(Boolean).join("\n");
  return window.confirm(text) ? Promise.resolve() : Promise.reject(new Error(""));
};

const dateString = (date) => (
  `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`
);

const todayString = () => dateString(new Date());

const daysAgoString = (daysAgo) => {
  const target = new Date();
  target.setDate(target.getDate() - daysAgo);
  return dateString(target);
};

const defaultOrderDeliveryDate = () => {
  const now = new Date();
  const target = new Date(now);
  if (now.getHours() >= 12) {
    target.setDate(target.getDate() + 1);
  }
  return dateString(target);
};

const defaultOrderFilters = () => {
  return {
    keyword: "",
    delivery_date: defaultOrderDeliveryDate(),
    meal_type: "lunch",
    status: "confirmed",
  };
};

createApp({
  setup() {
    const readInitialTab = () => {
      const tab = (window.location.hash || "").replace("#", "");
      return ["users", "orders", "menu", "ledger"].includes(tab) ? tab : "orders";
    };

    const activeTab = ref(readInitialTab());
    const navMenuOpen = ref(false);
    const loading = ref(false);
    const adminMeta = ref({ env: "-", mode: "-", updatedAt: "" });

    const userLoading = ref(false);
    const users = ref([]);
    const userTotal = ref(0);
    const userKeyword = ref("");
    const userToolsOpen = ref(false);
    const zeroSpendCollapsed = ref(true);
    const selectedUserDetail = ref(null);
    const userDetailLoading = ref(false);

    const orderLoading = ref(false);
    const orders = ref([]);
    const orderTotal = ref(0);
    const orderStatusCounts = ref([]);
    const orderLastUpdatedAt = ref("");
    const orderFilters = ref(defaultOrderFilters());
    const selectedOrder = ref(null);
    const orderDetailOpen = ref(false);
    const manualRefundingOrderNo = ref("");
    const refundConfirm = ref({ open: false, order: null, message: "", error: "" });
    const deliverySummaryOpen = ref(false);
    const deliverySummaryLoading = ref(false);
    const deliverySummaryOrders = ref([]);
    const deliverySummaryNote = ref("");

    const menuLoading = ref(false);
    const categories = ref([]);
    const dishes = ref([]);
    const menuSearch = ref("");
    const selectedCategoryId = ref("all");
    const financeLoading = ref(false);
    const financeDays = ref(7);
    const financeRangeMode = ref("7");
    const financeCustomRange = ref({
      start_date: daysAgoString(6),
      end_date: todayString(),
    });
    const financeReport = ref(null);
    const categoryEditor = ref({ open: false, mode: "create", id: null, name: "", sort_order: 0, is_active: true });
    const dishEditor = ref({
      open: false,
      mode: "create",
      id: null,
      category_id: null,
      name: "",
      description: "",
      detail_content: "",
      image_url: "",
      price: "",
      cost_price: "",
      stock: -1,
      sort_order: 0,
      is_active: true,
      is_sold_out: false,
    });

    const statusOrder = ["unpaid", "confirmed", "delivering", "completed", "refunded", "closed"];

    const statusLabel = (status) => ({
      unpaid: "待支付",
      confirmed: "已确认",
      delivering: "处理中",
      completed: "已完成",
      refunded: "已退款",
      closed: "已关闭",
    }[status] || status || "-");

    const statusClass = (status) => ({
      unpaid: "warning",
      confirmed: "primary",
      delivering: "success",
      completed: "success",
      refunded: "danger",
      closed: "danger",
    }[status] || "");

    const mealLabel = (mealType) => ({
      lunch: "午餐",
      dinner: "晚餐",
    }[mealType] || mealType || "-");

    const boolLabel = (value) => (value ? "是" : "否");
    const totalSpentNumber = (user) => Number(user?.total_spent || 0) || 0;
    const money = (value) => `¥${Number(value || 0).toFixed(2)}`;
    const formatTime = (value) => {
      if (!value) return "-";
      const time = new Date(value);
      if (Number.isNaN(time.getTime())) return String(value);
      return time.toLocaleString("zh-CN", { hour12: false });
    };

    const shortText = (value, length = 28) => {
      if (value === null || value === undefined || value === "") return "-";
      const text = String(value);
      return text.length > length ? `${text.slice(0, length)}...` : text;
    };

    const middleText = (value, length = 10) => {
      const text = String(value || "").trim() || "未填写昵称";
      const chars = Array.from(text);
      if (chars.length <= length) return text;
      const remaining = Math.max(length - 3, 2);
      const headLength = Math.ceil(remaining / 2);
      const tailLength = Math.floor(remaining / 2);
      return `${chars.slice(0, headLength).join("")}...${chars.slice(-tailLength).join("")}`;
    };

    const formatCell = (user, key) => {
      const value = user[key];
      if (key === "id") return formatUserId(value);
      if (key.startsWith("is_")) return boolLabel(Boolean(value));
      if (key.endsWith("_at")) return formatTime(value);
      if (value === null || value === undefined || value === "") return "-";
      return String(value);
    };

    const formatUserId = (value) => {
      const id = Number(value || 0);
      if (!Number.isFinite(id) || id <= 0) return "0000";
      return String(Math.trunc(id)).padStart(4, "0");
    };

    const avatarText = (user) => {
      const text = String(user?.nickname || user?.public_uid || user?.id || "U").trim() || "U";
      return (Array.from(text)[0] || "U").toUpperCase();
    };
    const compactUserName = (user) => middleText(user?.nickname || "未填写昵称", 10);

    const sortedUsers = computed(() => [...users.value].sort((a, b) => {
      const amountDiff = totalSpentNumber(b) - totalSpentNumber(a);
      if (amountDiff) return amountDiff;
      return Number(b.id || 0) - Number(a.id || 0);
    }));

    const zeroSpendUsers = computed(() => sortedUsers.value.filter((user) => totalSpentNumber(user) <= 0));
    const payingUsers = computed(() => sortedUsers.value.filter((user) => totalSpentNumber(user) > 0));
    const isUserSearching = computed(() => Boolean(userKeyword.value.trim()));
    const visibleUsers = computed(() => {
      if (isUserSearching.value) return sortedUsers.value;
      return zeroSpendCollapsed.value ? payingUsers.value : sortedUsers.value;
    });

    const toggleZeroSpendUsers = () => {
      zeroSpendCollapsed.value = !zeroSpendCollapsed.value;
    };

    const openUserTools = () => {
      userToolsOpen.value = true;
    };

    const closeUserTools = () => {
      userToolsOpen.value = false;
    };

    const openUserDetail = async (user) => {
      const requestedUserId = user.id;
      selectedUserDetail.value = {
        phone: "",
        points: 0,
        order_count: 0,
        created_at: null,
        member_joined_at: null,
        ...user,
      };
      userDetailLoading.value = true;

      try {
        const detail = await api.getRawUser(requestedUserId);
        if (selectedUserDetail.value && selectedUserDetail.value.id === requestedUserId) {
          selectedUserDetail.value = {
            ...selectedUserDetail.value,
            ...detail,
            phone: detail.phone || "",
            points: detail.points || 0,
            order_count: detail.order_count || 0,
          };
        }
      } catch (error) {
        showToast(error.message || "用户详情加载失败");
      } finally {
        userDetailLoading.value = false;
      }
    };

    const closeUserDetail = () => {
      selectedUserDetail.value = null;
      userDetailLoading.value = false;
    };

    const categoryMap = computed(() => {
      const map = new Map();
      categories.value.forEach((item) => map.set(Number(item.id), item));
      return map;
    });
    const hasSnackCategory = computed(() => categories.value.some((category) => category.name === "小食"));

    const dishCountsByCategory = computed(() => {
      const map = new Map();
      dishes.value.forEach((dish) => {
        const key = Number(dish.category_id);
        map.set(key, (map.get(key) || 0) + 1);
      });
      return map;
    });

    const filteredDishes = computed(() => {
      const keyword = menuSearch.value.trim().toLowerCase();
      return dishes.value.filter((dish) => {
        const matchCategory = selectedCategoryId.value === "all" || Number(dish.category_id) === Number(selectedCategoryId.value);
        const searchText = `${dish.name || ""} ${dish.description || ""} ${dish.detail_content || ""}`.toLowerCase();
        return matchCategory && (!keyword || searchText.includes(keyword));
      });
    });

    const orderGroups = computed(() => {
      const groups = [];
      statusOrder.forEach((status) => {
        const items = orders.value.filter((order) => order.status === status);
        if (items.length) {
          groups.push({ status, label: statusLabel(status), items });
        }
      });
      return groups;
    });

    const orderSummary = computed(() => {
      const getCount = (key) => orderStatusCounts.value.find((item) => item.key === key)?.count || 0;
      const refunded = getCount("refunded");
      const closed = getCount("closed") + refunded;
      return {
        total: orderTotal.value,
        unpaid: getCount("unpaid"),
        confirmed: getCount("confirmed"),
        delivering: getCount("delivering"),
        completed: getCount("completed"),
        refunded,
        closed,
      };
    });

    const activeOrderStatuses = new Set(["confirmed", "delivering", "completed"]);
    const printableOrderStatuses = activeOrderStatuses;

    const canPrintOrder = (order) => printableOrderStatuses.has(order?.status);

    const normalizeAddress = (address) => String(address || "")
      .replace(/[０-９]/g, (char) => String.fromCharCode(char.charCodeAt(0) - 0xfee0))
      .replace(/\s+/g, " ")
      .trim();

    const ALLOWED_AREAS = ["男寝", "女寝", "书4", "书5", "男9", "女9", "男7", "东区"];

    const deliveryArea = (address) => {
      const text = normalizeAddress(address);
      if (!text) return "未填写地址";

      for (const area of ALLOWED_AREAS) {
        if (text.startsWith(area)) return area;
      }
      return "未填写地址";
    };

    const deliverySummaryRows = computed(() => {
      const map = new Map();
      deliverySummaryOrders.value.forEach((order) => {
        const area = deliveryArea(order.delivery_address);
        const current = map.get(area) || { area, count: 0, samples: [] };
        current.count += 1;
        if (order.delivery_address && current.samples.length < 2 && !current.samples.includes(order.delivery_address)) {
          current.samples.push(order.delivery_address);
        }
        map.set(area, current);
      });

      return Array.from(map.values())
        .map((row) => ({
          ...row,
          sample: row.samples.length ? row.samples.join(" / ") : "未填写具体地址",
        }))
        .sort((a, b) => b.count - a.count || a.area.localeCompare(b.area, "zh-Hans-CN", { numeric: true }));
    });

    const deliverySummaryTotal = computed(() => deliverySummaryRows.value.reduce((sum, row) => sum + row.count, 0));

    const deliverySummaryFilterText = computed(() => {
      const filters = orderFilters.value;
      const parts = [
        filters.delivery_date || "全部日期",
        filters.meal_type ? mealLabel(filters.meal_type) : "全部餐别",
        filters.status ? statusLabel(filters.status) : "全部状态",
      ];
      if (filters.keyword) parts.push(`关键词：${filters.keyword}`);
      return parts.join(" · ");
    });

    const parseItemSummary = (summary) => {
      if (!summary) return [];
      return String(summary)
        .split(/[，,、]/)
        .map((part) => part.trim())
        .filter(Boolean)
        .map((part) => {
          const match = part.match(/^(.*?)[xX×*]\s*(\d+)$/);
          if (!match) return { name: part, quantity: 1 };
          return { name: match[1].trim(), quantity: Number(match[2] || 1) };
        })
        .filter((item) => item.name && item.quantity > 0);
    };

    const orderItemsFromSummary = (order) => parseItemSummary(order?.item_summary);
    const orderItemCount = (order) => {
      const explicitCount = Number(order?.item_count || 0);
      if (explicitCount > 0) return explicitCount;
      return orderItemsFromSummary(order).reduce((sum, item) => sum + Number(item.quantity || 0), 0);
    };
    const orderItemChips = (order, limit = 6) => orderItemsFromSummary(order).slice(0, limit);
    const orderExtraItemCount = (order, limit = 6) => Math.max(orderItemsFromSummary(order).length - limit, 0);
    const compactOrderNo = (orderNo) => {
      const text = String(orderNo || "");
      if (text.length <= 14) return text || "-";
      return `${text.slice(0, 8)}...${text.slice(-4)}`;
    };

    const MERCHANT_LABELS = { ej: "二斤皮", sl: "广式烧腊", xj: "徐记木子鸡", sd: "赛杜甄选" };

    const buildDishMerchantMap = () => {
      const map = new Map();
      for (const dish of dishes.value) {
        const code = dish.merchant_code || "";
        map.set(dish.name, MERCHANT_LABELS[code] || code || "未分类");
      }
      return map;
    };

    const buildMerchantReceiptText = async (mealType, options = {}) => {
      const includeEmpty = options.includeEmpty !== false;
      const deliveryDate = orderFilters.value.delivery_date || defaultOrderDeliveryDate();
      if (!dishes.value.length || !categories.value.length) {
        await loadMenu();
      }
      const list = await api.getOrders({
        meal_type: mealType,
        delivery_date: deliveryDate,
        include_refunded: "false",
      });
      const totals = new Map();
      (list || [])
        .filter((order) => activeOrderStatuses.has(order.status))
        .flatMap((order) => parseItemSummary(order.item_summary))
        .forEach((item) => {
          totals.set(item.name, (totals.get(item.name) || 0) + item.quantity);
        });

      if (!totals.size) {
        return includeEmpty ? `${deliveryDate} ${mealLabel(mealType)}\n暂无需要备餐的有效订单` : "";
      }

      const merchantMap = buildDishMerchantMap();
      const dishOrder = new Map(dishes.value.map((dish, idx) => [dish.name, Number(dish.sort_order ?? idx)]));
      const rows = Array.from(totals.entries())
        .map(([name, quantity]) => ({ name, quantity, merchant: merchantMap.get(name) || "未分类" }))
        .sort((a, b) => {
          const merchantDiff = a.merchant.localeCompare(b.merchant, "zh-CN");
          if (merchantDiff) return merchantDiff;
          const dishDiff = (dishOrder.get(a.name) ?? 9999) - (dishOrder.get(b.name) ?? 9999);
          if (dishDiff) return dishDiff;
          return a.name.localeCompare(b.name, "zh-CN");
        });

      const lines = [`${deliveryDate} ${mealLabel(mealType)}商家回执`];
      let currentMerchant = null;
      const allSameMerchant = rows.every((r) => r.merchant === rows[0].merchant);
      rows.forEach((item) => {
        if (!allSameMerchant && item.merchant !== currentMerchant) {
          currentMerchant = item.merchant;
          if (lines.length > 1) lines.push("");
          lines.push(`=====【${item.merchant}】=====`);
        }
        lines.push(`${item.name}*${item.quantity}份`);
      });
      lines.push("");
      lines.push(`#####合计《${Array.from(totals.values()).reduce((sum, count) => sum + count, 0)}》份#####`);
      return lines.join("\n");
    };

    const buildCombinedMerchantReceiptText = async () => {
      const lunchText = await buildMerchantReceiptText("lunch");
      const dinnerText = await buildMerchantReceiptText("dinner", { includeEmpty: false });
      return [lunchText, dinnerText].filter(Boolean).join("\n\n");
    };

    const copyMerchantReceipt = async () => {
      try {
        const text = await buildCombinedMerchantReceiptText();
        await copyText(text, "商家回执已复制");
      } catch (error) {
        showToast(error.message || "商家回执生成失败");
      }
    };

    const menuSummary = computed(() => ({
      categories: categories.value.length,
      dishes: dishes.value.length,
      active: dishes.value.filter((dish) => dish.is_active).length,
      soldOut: dishes.value.filter((dish) => dish.is_sold_out).length,
    }));

    const emptyFinanceSummary = {
      start_date: "",
      end_date: "",
      order_count: 0,
      item_count: 0,
      gross_amount: "0.00",
      product_amount: "0.00",
      delivery_fee: "0.00",
      discount_amount: "0.00",
      revenue_amount: "0.00",
      cost_amount: "0.00",
      profit_amount: "0.00",
      profit_rate: "0.00",
      average_order_amount: "0.00",
      missing_cost_items: 0,
    };
    const financeSummary = computed(() => financeReport.value?.summary || emptyFinanceSummary);
    const financeDishRows = computed(() => (financeReport.value?.dish_rows || []).slice(0, 5));
    const financeRevenueLabel = computed(() => (
      financeRangeMode.value === "custom" ? "区间流水" : `${Number(financeRangeMode.value || financeDays.value || 7)}天流水`
    ));

    const setTab = async (tab) => {
      activeTab.value = tab;
      if (window.location.hash !== `#${tab}`) {
        window.location.hash = tab;
      }
      if (tab === "users" && !users.value.length) await loadUsers();
      if (tab === "orders" && !orders.value.length) await loadOrders();
      if (tab === "menu" && !dishes.value.length) await loadMenu();
      if (tab === "ledger" && !financeReport.value) await loadFinance();
    };

    const toggleNavMenu = () => {
      navMenuOpen.value = !navMenuOpen.value;
    };

    const closeNavMenu = () => {
      navMenuOpen.value = false;
    };

    const openTabFromMenu = async (tab) => {
      closeNavMenu();
      await setTab(tab);
    };

    const loadMeta = async () => {
      try {
        const overview = await api.getOperationsOverview(todayString());
        adminMeta.value = {
          env: overview.app_env || "-",
          mode: overview.payment_mode || "-",
          updatedAt: formatTime(new Date().toISOString()),
        };
      } catch (error) {
        adminMeta.value.updatedAt = "概览读取失败";
      }
    };

    const loadUsers = async () => {
      userLoading.value = true;
      try {
        const params = { page: 1, page_size: 500 };
        if (userKeyword.value.trim()) params.keyword = userKeyword.value.trim();
        const result = await api.getRawUsers(params);
        users.value = result.items || [];
        userTotal.value = result.total || 0;
        zeroSpendCollapsed.value = !userKeyword.value.trim();
      } catch (error) {
        showToast(error.message || "用户数据加载失败");
      } finally {
        userLoading.value = false;
      }
    };

    const resetUserSearch = async () => {
      userKeyword.value = "";
      await loadUsers();
    };

    const applyUserTools = async () => {
      await loadUsers();
      closeUserTools();
    };

    const resetUserTools = async () => {
      await resetUserSearch();
      closeUserTools();
    };

    const buildOrderParams = () => {
      const params = { page: 1, page_size: 100, include_refunded: "true" };
      Object.entries(orderFilters.value).forEach(([key, value]) => {
        if (value) params[key] = value;
      });
      return params;
    };

    const loadOrders = async ({ silent = false } = {}) => {
      if (!silent) orderLoading.value = true;
      try {
        const result = await api.getOrderMonitor(buildOrderParams());
        orders.value = result.items || [];
        orderTotal.value = result.total || 0;
        orderStatusCounts.value = result.status_counts || [];
        orderLastUpdatedAt.value = result.last_updated_at || "";
      } catch (error) {
        showToast(error.message || "订单数据加载失败");
      } finally {
        if (!silent) orderLoading.value = false;
      }
    };

    const openDeliverySummary = async () => {
      deliverySummaryOpen.value = true;
      deliverySummaryLoading.value = true;
      deliverySummaryNote.value = "";

      try {
        const baseParams = { ...buildOrderParams(), page_size: 100 };
        const allOrders = [];
        let page = 1;
        let total = 0;

        do {
          const result = await api.getOrderMonitor({ ...baseParams, page });
          const items = result.items || [];
          total = Number(result.total || items.length || 0);
          allOrders.push(...items);
          page += 1;
          if (!items.length) break;
        } while (allOrders.length < total && page <= 50);

        deliverySummaryOrders.value = allOrders;
        if (total > allOrders.length) {
          deliverySummaryNote.value = `当前统计已读取 ${allOrders.length} / ${total} 单，后续页未继续拉取。`;
        }
      } catch (error) {
        deliverySummaryOrders.value = orders.value;
        deliverySummaryNote.value = "完整配送详情读取失败，当前展示页面已加载订单的统计。";
        showToast(error.message || "配送详情加载失败");
      } finally {
        deliverySummaryLoading.value = false;
      }
    };

    const closeDeliverySummary = () => {
      deliverySummaryOpen.value = false;
    };

    const resetOrderFilters = () => {
      orderFilters.value = defaultOrderFilters();
      loadOrders();
    };

    const openOrder = async (order) => {
      try {
        selectedOrder.value = await api.getOrderDetail(order.order_no);
        orderDetailOpen.value = true;
      } catch (error) {
        showToast(error.message || "订单详情加载失败");
      }
    };

    const refreshSelectedOrder = async () => {
      if (!selectedOrder.value?.order_no) return;
      selectedOrder.value = await api.getOrderDetail(selectedOrder.value.order_no);
    };

    const markOrder = async (order, targetStatus) => {
      const text = targetStatus === "completed" ? "确认将订单标记为已完成？" : "确认将订单标记为处理中？";
      try {
        await showConfirmDialog({ title: "确认订单操作", message: text });
        let detail = null;
        if (targetStatus === "delivering") {
          detail = await api.markOrderDelivering(order.order_no);
        } else {
          detail = await api.completeOrder(order.order_no);
        }
        selectedOrder.value = detail;
        showToast("订单状态已更新");
        await loadOrders({ silent: true });
      } catch (error) {
        if (error && error.message) showToast(error.message);
      }
    };

    const canManualRefund = (order) => ["confirmed", "delivering", "completed"].includes(order?.status);

    const manualRefund = async (order) => {
      if (!order?.order_no) {
        showToast("缺少订单号");
        return;
      }
      if (!canManualRefund(order)) {
        showToast("当前状态不支持手动退款");
        return;
      }
      if (manualRefundingOrderNo.value) return;
      refundConfirm.value = { open: true, order, message: "", error: "" };
    };

    const closeRefundConfirm = () => {
      if (manualRefundingOrderNo.value) return;
      refundConfirm.value = { open: false, order: null, message: "", error: "" };
    };

    const confirmManualRefund = async () => {
      const order = refundConfirm.value.order;
      if (!order?.order_no || manualRefundingOrderNo.value) return;
      manualRefundingOrderNo.value = order.order_no;
      refundConfirm.value = { ...refundConfirm.value, message: "正在提交退款标记...", error: "" };
      try {
        showToast("正在手动退款...");
        const detail = await api.manualRefundOrder(order.order_no);
        if (selectedOrder.value?.order_no === order.order_no) {
          selectedOrder.value = detail;
        }
        showToast("订单已手动退款");
        refundConfirm.value = { open: false, order: null, message: "", error: "" };
        await loadOrders({ silent: true });
      } catch (error) {
        const message = error?.message || "手动退款失败";
        refundConfirm.value = { ...refundConfirm.value, message: "", error: message };
        showToast(message);
      } finally {
        manualRefundingOrderNo.value = "";
      }
    };

    const handleNativeRefundConfirmClick = (event) => {
      const target = event.target?.closest?.("[data-refund-confirm]");
      if (!target) return;
      event.preventDefault();
      event.stopPropagation();
      confirmManualRefund();
    };

    const printReceipt = (orderNo, options = {}) => {
      if (!orderNo) {
        showToast("缺少订单号");
        return;
      }
      const settings = {
        autoprint: true,
        queue: false,
        batch: false,
        ...options,
      };
      const params = new URLSearchParams(settings.batch ? { batch: "1" } : { order_no: String(orderNo) });
      params.set("v", PRINT_PAGE_VERSION);
      if (settings.autoprint) params.set("autoprint", "1");
      if (settings.queue) params.set("queue", "1");
      window.open(`receipt-print.html?${params.toString()}`, "_blank", "width=520,height=900");
    };

    const printFilteredOrders = async () => {
      const orderNos = Array.from(
        new Set(
          orders.value
            .filter(canPrintOrder)
            .map((order) => order?.order_no)
            .filter((orderNo) => typeof orderNo === "string" && orderNo.length)
        )
      );
      if (!orderNos.length) {
        showToast("当前没有可打印订单，仅打印已确认、处理中、已完成");
        return;
      }

      try {
        await showConfirmDialog({
          title: "确认批量打印",
          message: `将当前结果中的 ${orderNos.length} 个有效订单排成 A4 紧凑小票并打印，已关闭、已退款、待支付订单不会打印。是否继续？`,
        });
        window.localStorage.setItem(PRINT_QUEUE_KEY, JSON.stringify(orderNos));
        printReceipt(orderNos[0], { autoprint: true, batch: true });
        showToast(`已开始批量打印 ${orderNos.length} 单`);
      } catch (error) {
        if (error && error.message) showToast(error.message);
      }
    };

    const formatFlavors = (flavors) => {
      if (!flavors) return "";
      if (typeof flavors === "string") return flavors;
      return Object.entries(flavors)
        .filter(([, value]) => value !== null && value !== "" && JSON.stringify(value) !== "[]" && JSON.stringify(value) !== "{}")
        .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join("/") : value}`)
        .join("；");
    };

    const copyText = async (text, success = "已复制") => {
      if (!text) {
        showToast("没有可复制内容");
        return;
      }
      try {
        if (navigator.clipboard?.writeText) {
          await navigator.clipboard.writeText(text);
        } else {
          throw new Error("clipboard unavailable");
        }
        showToast(success);
      } catch (error) {
        const textarea = document.createElement("textarea");
        textarea.value = text;
        textarea.setAttribute("readonly", "readonly");
        textarea.style.position = "fixed";
        textarea.style.left = "-9999px";
        document.body.appendChild(textarea);
        textarea.select();
        const ok = document.execCommand("copy");
        document.body.removeChild(textarea);
        showToast(ok ? success : "复制失败，请手动选择文本复制");
      }
    };

    const buildFinanceParams = () => {
      if (financeRangeMode.value === "custom") {
        const startDate = financeCustomRange.value.start_date;
        const endDate = financeCustomRange.value.end_date;
        if (!startDate || !endDate) {
          throw new Error("请选择开始日期和结束日期");
        }
        if (startDate > endDate) {
          throw new Error("开始日期不能晚于结束日期");
        }
        return { start_date: startDate, end_date: endDate };
      }

      const days = Number(financeRangeMode.value || financeDays.value || 7);
      financeDays.value = days;
      return { days };
    };

    const loadFinance = async () => {
      financeLoading.value = true;
      try {
        financeReport.value = await api.getReconciliation(buildFinanceParams());
      } catch (error) {
        showToast(error.message || "对账数据加载失败");
      } finally {
        financeLoading.value = false;
      }
    };

    const handleFinanceRangeChange = () => {
      if (financeRangeMode.value !== "custom") {
        financeDays.value = Number(financeRangeMode.value || 7);
        loadFinance();
      }
    };

    const loadMenu = async () => {
      menuLoading.value = true;
      try {
        const [categoryList, dishList] = await Promise.all([
          api.getCategories(),
          api.getDishes({ page: 1, page_size: 500 }),
        ]);
        categories.value = categoryList || [];
        dishes.value = dishList || [];
        if (selectedCategoryId.value !== "all" && !categories.value.some((item) => Number(item.id) === Number(selectedCategoryId.value))) {
          selectedCategoryId.value = "all";
        }
      } catch (error) {
        showToast(error.message || "菜单数据加载失败");
      } finally {
        menuLoading.value = false;
      }
    };

    const categoryName = (categoryId) => categoryMap.value.get(Number(categoryId))?.name || `分类 ${categoryId}`;

    const openCategoryEditor = (category = null) => {
      categoryEditor.value = category
        ? { open: true, mode: "edit", id: category.id, name: category.name, sort_order: category.sort_order, is_active: Boolean(category.is_active) }
        : { open: true, mode: "create", id: null, name: "", sort_order: categories.value.length * 10 + 10, is_active: true };
    };

    const closeCategoryEditor = () => {
      categoryEditor.value.open = false;
    };

    const submitCategory = async () => {
      const form = categoryEditor.value;
      if (!form.name.trim()) {
        showToast("请填写栏目名称");
        return;
      }
      const payload = {
        name: form.name.trim(),
        sort_order: Number(form.sort_order || 0),
        is_active: Boolean(form.is_active),
      };
      const isCreate = form.mode !== "edit";
      try {
        let savedCategory = null;
        if (form.mode === "edit") {
          savedCategory = await api.updateCategory(form.id, payload);
        } else {
          savedCategory = await api.createCategory(payload);
        }
        closeCategoryEditor();
        showToast("栏目已保存");
        await loadMenu();
        if (isCreate && dishEditor.value.open) {
          const createdCategory = categories.value.find((category) => (
            Number(category.id) === Number(savedCategory?.id) || category.name === payload.name
          ));
          if (createdCategory) {
            dishEditor.value.category_id = createdCategory.id;
          }
        }
      } catch (error) {
        showToast(error.message || "栏目保存失败");
      }
    };

    const deleteCategory = async (category) => {
      try {
        await showConfirmDialog({ title: "删除分类", message: `确认删除“${category.name}”？有菜品的分类会被后端拒绝删除。` });
        await api.deleteCategory(category.id);
        showToast("分类已删除");
        if (Number(selectedCategoryId.value) === Number(category.id)) selectedCategoryId.value = "all";
        await loadMenu();
      } catch (error) {
        if (error && error.message) showToast(error.message);
      }
    };

    const emptyDishForm = () => ({
      open: true,
      mode: "create",
      id: null,
      category_id: selectedCategoryId.value === "all" ? categories.value[0]?.id || null : Number(selectedCategoryId.value),
      name: "",
      description: "",
      detail_content: "",
      image_url: "",
      price: "",
      cost_price: "",
      merchant_code: "",
      stock: -1,
      sort_order: dishes.value.length * 10 + 10,
      is_active: true,
      is_sold_out: false,
    });

    const openDishEditor = (dish = null) => {
      dishEditor.value = dish
        ? {
            open: true,
            mode: "edit",
            id: dish.id,
            category_id: dish.category_id,
            name: dish.name || "",
            description: dish.description || "",
            detail_content: dish.detail_content || "",
            image_url: dish.image_url || "",
            price: String(dish.price || ""),
            cost_price: String(dish.cost_price || ""),
            merchant_code: dish.merchant_code || "",
            stock: dish.stock,
            sort_order: dish.sort_order,
            is_active: Boolean(dish.is_active),
            is_sold_out: Boolean(dish.is_sold_out),
          }
        : emptyDishForm();
    };

    const handleDishCategoryChange = () => {
      if (dishEditor.value.category_id !== NEW_CATEGORY_VALUE) return;
      dishEditor.value.category_id = categories.value[0]?.id || null;
      openCategoryEditor();
    };

    const closeDishEditor = () => {
      dishEditor.value.open = false;
    };

    const buildDishPayload = () => {
      const form = dishEditor.value;
      return {
        category_id: Number(form.category_id),
        name: form.name.trim(),
        description: form.description.trim(),
        detail_content: form.detail_content.trim(),
        image_url: form.image_url.trim(),
        price: Number(form.price),
        cost_price: Number(form.cost_price || 0),
        merchant_code: (form.merchant_code || "").trim() || null,
        stock: Number(form.stock),
        sort_order: Number(form.sort_order),
        is_active: Boolean(form.is_active),
        is_sold_out: Boolean(form.is_sold_out),
      };
    };

    const validateDishPayload = (payload) => {
      if (!payload.name) return "请填写菜品名称";
      if (!payload.category_id) return "请选择分类";
      if (!Number.isFinite(payload.price) || payload.price < 0) return "请填写有效价格";
      if (!Number.isFinite(payload.cost_price) || payload.cost_price < 0) return "请填写有效成本";
      if (!Number.isFinite(payload.stock)) return "请填写有效库存";
      if (!Number.isFinite(payload.sort_order)) return "请填写有效排序";
      return "";
    };

    const submitDish = async () => {
      const payload = buildDishPayload();
      const validationError = validateDishPayload(payload);
      if (validationError) {
        showToast(validationError);
        return;
      }
      try {
        if (dishEditor.value.mode === "edit") {
          await api.updateDish(dishEditor.value.id, payload);
        } else {
          await api.createDish(payload);
        }
        closeDishEditor();
        showToast("菜品已保存");
        await loadMenu();
      } catch (error) {
        showToast(error.message || "菜品保存失败");
      }
    };

    const patchDish = async (dish, patch, successMessage) => {
      try {
        await api.updateDish(dish.id, _buildDishUpdatePayload(dish, patch));
        showToast(successMessage);
        await loadMenu();
      } catch (error) {
        showToast(error.message || "菜品更新失败");
      }
    };

    const deleteDish = async (dish) => {
      try {
        await showConfirmDialog({ title: "删除菜品", message: `确认删除“${dish.name}”？` });
        await api.deleteDish(dish.id);
        showToast("菜品已删除");
        await loadMenu();
      } catch (error) {
        if (error && error.message) showToast(error.message);
      }
    };

    const _buildDishUpdatePayload = (dish, overrides = {}) => ({
      category_id: Number(dish.category_id),
      name: dish.name,
      description: dish.description || "",
      detail_content: dish.detail_content || "",
      image_url: dish.image_url || "",
      price: Number(dish.price),
      cost_price: Number(dish.cost_price || 0),
      merchant_code: dish.merchant_code || null,
      stock: Number(dish.stock),
      sort_order: Number(dish.sort_order),
      is_active: Boolean(dish.is_active),
      is_sold_out: Boolean(dish.is_sold_out),
      ...overrides,
    });

    const _batchUpdateDishes = async (filterFn, overrides, successMsg) => {
      const targets = dishes.value.filter(filterFn);
      if (!targets.length) { showToast("没有需要操作的菜品"); return; }
      await Promise.all(targets.map((d) => api.updateDish(d.id, _buildDishUpdatePayload(d, overrides))));
      showToast(successMsg(targets.length));
      await loadMenu();
    };

    const batchSoldOut = async () => {
      await showConfirmDialog({ title: "一键售罄", message: "确认将所有菜品标记为售罄？" });
      await _batchUpdateDishes(
        (d) => d.is_active && !d.is_sold_out,
        { is_sold_out: true },
        (n) => `已售罄 ${n} 款菜品`
      );
    };

    const batchRestock = async () => {
      await showConfirmDialog({ title: "一键补货", message: "确认将所有售罄菜品恢复上架？" });
      await _batchUpdateDishes(
        (d) => d.is_sold_out,
        { is_sold_out: false, is_active: true },
        (n) => `已补货 ${n} 款菜品`
      );
    };

    const logoutAdmin = () => {
      logout();
    };

    onMounted(async () => {
      window.__sydrooConfirmManualRefund = confirmManualRefund;
      document.addEventListener("click", handleNativeRefundConfirmClick, true);
      loading.value = true;
      try {
        const initialLoads = [loadMeta(), loadUsers(), loadOrders(), loadMenu()];
        if (activeTab.value === "ledger") initialLoads.push(loadFinance());
        await Promise.all(initialLoads);
      } finally {
        loading.value = false;
      }
    });

    return {
      activeTab,
      NEW_CATEGORY_VALUE,
      navMenuOpen,
      loading,
      adminMeta,
      API_BASE_URL,
      userLoading,
      users,
      visibleUsers,
      zeroSpendUsers,
      payingUsers,
      isUserSearching,
      zeroSpendCollapsed,
      userTotal,
      userKeyword,
      userToolsOpen,
      selectedUserDetail,
      userDetailLoading,
      orderLoading,
      orders,
      orderTotal,
      orderStatusCounts,
      orderLastUpdatedAt,
      orderFilters,
      selectedOrder,
      orderDetailOpen,
      manualRefundingOrderNo,
      refundConfirm,
      deliverySummaryOpen,
      deliverySummaryLoading,
      deliverySummaryRows,
      deliverySummaryTotal,
      deliverySummaryFilterText,
      deliverySummaryNote,
      orderGroups,
      orderItemCount,
      orderItemChips,
      orderExtraItemCount,
      compactOrderNo,
      orderSummary,
      menuLoading,
      categories,
      dishes,
      menuSearch,
      selectedCategoryId,
      financeLoading,
      financeDays,
      financeRangeMode,
      financeCustomRange,
      financeReport,
      financeSummary,
      financeDishRows,
      financeRevenueLabel,
      categoryEditor,
      dishEditor,
      categoryMap,
      hasSnackCategory,
      dishCountsByCategory,
      filteredDishes,
      menuSummary,
      setTab,
      toggleNavMenu,
      closeNavMenu,
      openTabFromMenu,
      loadUsers,
      resetUserSearch,
      applyUserTools,
      resetUserTools,
      openUserTools,
      closeUserTools,
      toggleZeroSpendUsers,
      openUserDetail,
      closeUserDetail,
      loadOrders,
      resetOrderFilters,
      openDeliverySummary,
      closeDeliverySummary,
      copyMerchantReceipt,
      openOrder,
      markOrder,
      canManualRefund,
      canPrintOrder,
      manualRefund,
      closeRefundConfirm,
      confirmManualRefund,
      printReceipt,
      printFilteredOrders,
      formatFlavors,
      copyText,
      loadFinance,
      handleFinanceRangeChange,
      loadMenu,
      categoryName,
      openCategoryEditor,
      closeCategoryEditor,
      submitCategory,
      deleteCategory,
      openDishEditor,
      handleDishCategoryChange,
      closeDishEditor,
      submitDish,
      patchDish,
      deleteDish,
      batchSoldOut,
      batchRestock,
      logoutAdmin,
      statusLabel,
      statusClass,
      mealLabel,
      boolLabel,
      money,
      formatTime,
      shortText,
      middleText,
      compactUserName,
      formatCell,
      formatUserId,
      avatarText,
      loadMeta,
    };
  },
}).use(vant).mount("#app");
