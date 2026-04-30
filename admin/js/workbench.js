checkAuth();

const { createApp, ref, computed, onMounted } = Vue;
const PRINT_QUEUE_KEY = "sydroo_order_print_queue_v1";
const PRINT_PAGE_VERSION = "20260428-0235";

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
      return ["users", "orders", "menu"].includes(tab) ? tab : "users";
    };

    const activeTab = ref(readInitialTab());
    const loading = ref(false);
    const adminMeta = ref({ env: "-", mode: "-", updatedAt: "" });

    const userLoading = ref(false);
    const users = ref([]);
    const userTotal = ref(0);
    const userKeyword = ref("");
    const userColumns = [
      "id",
      "openid",
      "public_uid",
      "nickname",
      "avatar_url",
      "phone",
      "is_registered",
      "is_member",
      "invite_code",
      "invited_by_user_id",
      "points",
      "total_spent",
      "registered_at",
      "member_joined_at",
      "created_at",
      "updated_at",
      "order_count",
      "coupon_count",
    ];
    const userColumnLabels = {
      id: "用户ID",
      openid: "微信OpenID",
      public_uid: "用户编号",
      nickname: "昵称",
      avatar_url: "头像链接",
      phone: "手机号",
      is_registered: "已注册",
      is_member: "会员",
      invite_code: "邀请码",
      invited_by_user_id: "邀请人ID",
      points: "积分",
      total_spent: "累计消费",
      registered_at: "注册时间",
      member_joined_at: "会员开通时间",
      created_at: "创建时间",
      updated_at: "更新时间",
      order_count: "订单数",
      coupon_count: "优惠券数",
    };

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

    const menuLoading = ref(false);
    const categories = ref([]);
    const dishes = ref([]);
    const menuSearch = ref("");
    const selectedCategoryId = ref("all");
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

    const formatCell = (user, key) => {
      const value = user[key];
      if (key.startsWith("is_")) return boolLabel(Boolean(value));
      if (key.endsWith("_at")) return formatTime(value);
      if (value === null || value === undefined || value === "") return "-";
      return String(value);
    };

    const avatarText = (user) => shortText(user.nickname || user.public_uid || user.id || "U", 1).toUpperCase();
    const userColumnLabel = (key) => userColumnLabels[key] || key;

    const categoryMap = computed(() => {
      const map = new Map();
      categories.value.forEach((item) => map.set(Number(item.id), item));
      return map;
    });

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

    const dishCategoryName = (dishName) => {
      const dish = dishes.value.find((item) => item.name === dishName);
      return dish ? categoryName(dish.category_id) : "其他";
    };

    const buildMerchantReceiptText = async (mealType) => {
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
        return `${deliveryDate} ${mealLabel(mealType)}\n暂无需要备餐的有效订单`;
      }

      const dishOrder = new Map(dishes.value.map((dish, index) => [dish.name, Number(dish.sort_order ?? index)]));
      const rows = Array.from(totals.entries())
        .map(([name, quantity]) => ({ name, quantity, category: dishCategoryName(name) }))
        .sort((a, b) => {
          const categoryDiff = (categories.value.find((item) => item.name === a.category)?.sort_order ?? 9999)
            - (categories.value.find((item) => item.name === b.category)?.sort_order ?? 9999);
          if (categoryDiff) return categoryDiff;
          const dishDiff = (dishOrder.get(a.name) ?? 9999) - (dishOrder.get(b.name) ?? 9999);
          if (dishDiff) return dishDiff;
          return a.name.localeCompare(b.name, "zh-CN");
        });

      const lines = [`${deliveryDate} ${mealLabel(mealType)}商家回执`];
      rows.forEach((item) => lines.push(`${item.name}*${item.quantity}份`));
      lines.push(`合计*${Array.from(totals.values()).reduce((sum, count) => sum + count, 0)}份`);
      return lines.join("\n");
    };

    const copyMerchantReceipt = async (mealType) => {
      try {
        const text = await buildMerchantReceiptText(mealType);
        await copyText(text, `${mealLabel(mealType)}商家回执已复制`);
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

    const setTab = async (tab) => {
      activeTab.value = tab;
      if (window.location.hash !== `#${tab}`) {
        window.location.hash = tab;
      }
      if (tab === "users" && !users.value.length) await loadUsers();
      if (tab === "orders" && !orders.value.length) await loadOrders();
      if (tab === "menu" && !dishes.value.length) await loadMenu();
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
      } catch (error) {
        showToast(error.message || "用户数据加载失败");
      } finally {
        userLoading.value = false;
      }
    };

    const resetUserSearch = () => {
      userKeyword.value = "";
      loadUsers();
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
        showToast("请填写分类名称");
        return;
      }
      const payload = {
        name: form.name.trim(),
        sort_order: Number(form.sort_order || 0),
        is_active: Boolean(form.is_active),
      };
      try {
        if (form.mode === "edit") {
          await api.updateCategory(form.id, payload);
        } else {
          await api.createCategory(payload);
        }
        closeCategoryEditor();
        showToast("分类已保存");
        await loadMenu();
      } catch (error) {
        showToast(error.message || "分类保存失败");
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
            stock: dish.stock,
            sort_order: dish.sort_order,
            is_active: Boolean(dish.is_active),
            is_sold_out: Boolean(dish.is_sold_out),
          }
        : emptyDishForm();
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
      const payload = {
        category_id: Number(dish.category_id),
        name: dish.name,
        description: dish.description || "",
        detail_content: dish.detail_content || "",
        image_url: dish.image_url || "",
        price: Number(dish.price),
        stock: Number(dish.stock),
        sort_order: Number(dish.sort_order),
        is_active: Boolean(dish.is_active),
        is_sold_out: Boolean(dish.is_sold_out),
        ...patch,
      };
      try {
        await api.updateDish(dish.id, payload);
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

    const logoutAdmin = () => {
      logout();
    };

    onMounted(async () => {
      window.__sydrooConfirmManualRefund = confirmManualRefund;
      document.addEventListener("click", handleNativeRefundConfirmClick, true);
      loading.value = true;
      try {
        await Promise.all([loadMeta(), loadUsers(), loadOrders(), loadMenu()]);
      } finally {
        loading.value = false;
      }
    });

    return {
      activeTab,
      loading,
      adminMeta,
      API_BASE_URL,
      userLoading,
      users,
      userTotal,
      userKeyword,
      userColumns,
      userColumnLabel,
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
      orderGroups,
      orderSummary,
      menuLoading,
      categories,
      dishes,
      menuSearch,
      selectedCategoryId,
      categoryEditor,
      dishEditor,
      categoryMap,
      dishCountsByCategory,
      filteredDishes,
      menuSummary,
      setTab,
      loadUsers,
      resetUserSearch,
      loadOrders,
      resetOrderFilters,
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
      loadMenu,
      categoryName,
      openCategoryEditor,
      closeCategoryEditor,
      submitCategory,
      deleteCategory,
      openDishEditor,
      closeDishEditor,
      submitDish,
      patchDish,
      deleteDish,
      logoutAdmin,
      statusLabel,
      statusClass,
      mealLabel,
      boolLabel,
      money,
      formatTime,
      shortText,
      formatCell,
      avatarText,
      loadMeta,
    };
  },
}).use(vant).mount("#app");
