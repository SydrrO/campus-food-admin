checkAuth();

const { createApp, ref, computed, onMounted } = Vue;

const getVantApi = () => window.vant || {};

const showToast = (message) => {
  const text = typeof message === "string" ? message : message?.message || String(message || "");
  const vantApi = getVantApi();
  if (typeof vantApi.showToast === "function") return vantApi.showToast(text);
  if (typeof vantApi.Toast === "function") return vantApi.Toast(text);
  window.alert(text);
  return null;
};

const showConfirmDialog = (options = {}) => {
  const vantApi = getVantApi();
  if (typeof vantApi.showConfirmDialog === "function") return vantApi.showConfirmDialog(options);
  if (typeof vantApi.Dialog?.confirm === "function") return vantApi.Dialog.confirm(options);
  const text = [options.title, options.message].filter(Boolean).join("\n");
  return window.confirm(text) ? Promise.resolve() : Promise.reject(new Error(""));
};

createApp({
  setup() {
    const userIdInput = ref(new URLSearchParams(window.location.search).get("user_id") || "");
    const selectedUser = ref(null);
    const coupons = ref([]);
    const navMenuOpen = ref(false);
    const loading = ref(false);
    const issueLoading = ref(false);
    const deletingCouponId = ref(null);
    const errorMessage = ref("");
    const lastUpdatedAt = ref("");
    const usedCouponDialogOpen = ref(false);
    const issueForm = ref({
      status: "available",
      amount: "0.50",
      count: 1,
      title: "",
    });

    const couponStats = computed(() => {
      const stats = {
        total: coupons.value.length,
        unrevealed: 0,
        available: 0,
        reserved: 0,
        used: 0,
      };
      coupons.value.forEach((coupon) => {
        if (Object.prototype.hasOwnProperty.call(stats, coupon.status)) {
          stats[coupon.status] += 1;
        }
      });
      return stats;
    });

    const visibleCoupons = computed(() => coupons.value.filter((coupon) => coupon.status !== "used"));
    const usedCoupons = computed(() => coupons.value.filter((coupon) => coupon.status === "used"));

    const normalizedUserId = () => {
      const raw = String(userIdInput.value || "").trim();
      if (!/^\d+$/.test(raw)) {
        return null;
      }
      const value = Number(raw);
      return Number.isSafeInteger(value) && value > 0 ? value : null;
    };

    const statusLabel = (status) => ({
      unrevealed: "未揭晓",
      available: "可使用",
      reserved: "锁定中",
      used: "已使用",
    }[status] || status || "-");

    const statusClass = (status) => ({
      unrevealed: "warning",
      available: "success",
      reserved: "primary",
      used: "danger",
    }[status] || "");

    const formatTime = (value) => {
      if (!value) return "-";
      const time = new Date(value);
      if (Number.isNaN(time.getTime())) return String(value);
      return time.toLocaleString("zh-CN", { hour12: false });
    };

    const money = (value) => `¥${Number(value || 0).toFixed(2)}`;

    const avatarText = (user) => {
      const text = String(user?.nickname || user?.public_uid || user?.id || "U");
      return text.slice(0, 1).toUpperCase();
    };

    const loadUserCoupons = async () => {
      const userId = normalizedUserId();
      if (!userId) {
        errorMessage.value = "请输入有效的用户 ID";
        selectedUser.value = null;
        coupons.value = [];
        return;
      }

      loading.value = true;
      errorMessage.value = "";
      try {
        const user = await api.getRawUser(userId);
        const userCoupons = await api.getUserCoupons(userId);
        selectedUser.value = user;
        coupons.value = userCoupons || [];
        lastUpdatedAt.value = formatTime(new Date().toISOString());
        const url = new URL(window.location.href);
        url.searchParams.set("user_id", String(userId));
        window.history.replaceState(null, "", url.toString());
      } catch (error) {
        selectedUser.value = null;
        coupons.value = [];
        errorMessage.value = error.message || "查询失败";
      } finally {
        loading.value = false;
      }
    };

    const resetPage = () => {
      userIdInput.value = "";
      selectedUser.value = null;
      coupons.value = [];
      errorMessage.value = "";
      lastUpdatedAt.value = "";
      usedCouponDialogOpen.value = false;
      window.history.replaceState(null, "", window.location.pathname);
    };

    const usePreset = (amount) => {
      issueForm.value.status = "available";
      issueForm.value.amount = amount;
      issueForm.value.title = "";
    };

    const buildIssuePayload = () => {
      const status = issueForm.value.status;
      const title = String(issueForm.value.title || "").trim();
      const payload = { status };
      if (title) {
        payload.title = title;
      }
      if (status === "available") {
        const amount = Number(issueForm.value.amount);
        if (!Number.isFinite(amount) || amount <= 0) {
          throw new Error("请填写有效金额");
        }
        payload.amount = amount.toFixed(2);
      }
      return payload;
    };

    const issueCoupons = async () => {
      const userId = normalizedUserId();
      if (!selectedUser.value || !userId) {
        showToast("请先查询用户");
        return;
      }

      const count = Number(issueForm.value.count || 1);
      if (!Number.isInteger(count) || count < 1 || count > 50) {
        showToast("数量必须在 1 到 50 之间");
        return;
      }

      let payload;
      try {
        payload = buildIssuePayload();
      } catch (error) {
        showToast(error.message || "发放参数有误");
        return;
      }

      issueLoading.value = true;
      try {
        for (let index = 0; index < count; index += 1) {
          await api.issueUserCoupon(userId, payload);
        }
        showToast(count > 1 ? `已发放 ${count} 张优惠券` : "优惠券已发放");
        await loadUserCoupons();
      } catch (error) {
        showToast(error.message || "发放失败");
      } finally {
        issueLoading.value = false;
      }
    };

    const canDeleteCoupon = (coupon) => ["unrevealed", "available"].includes(coupon.status);

    const openUsedCouponDialog = () => {
      usedCouponDialogOpen.value = true;
    };

    const closeUsedCouponDialog = () => {
      usedCouponDialogOpen.value = false;
    };

    const deleteCoupon = async (coupon) => {
      const userId = normalizedUserId();
      if (!userId || !coupon) return;
      if (!canDeleteCoupon(coupon)) {
        showToast("锁定中或已使用的优惠券不能删除");
        return;
      }

      try {
        await showConfirmDialog({
          title: "删除优惠券",
          message: `确认删除 #${coupon.id} ${coupon.display_title || coupon.title}？`,
        });
      } catch (error) {
        return;
      }

      deletingCouponId.value = coupon.id;
      try {
        await api.deleteUserCoupon(userId, coupon.id);
        showToast("优惠券已删除");
        await loadUserCoupons();
      } catch (error) {
        showToast(error.message || "删除失败");
      } finally {
        deletingCouponId.value = null;
      }
    };

    const logoutAdmin = () => {
      logout();
    };

    const toggleNavMenu = () => {
      navMenuOpen.value = !navMenuOpen.value;
    };

    const closeNavMenu = () => {
      navMenuOpen.value = false;
    };

    onMounted(() => {
      if (userIdInput.value) {
        loadUserCoupons();
      }
    });

    return {
      API_BASE_URL,
      userIdInput,
      selectedUser,
      coupons,
      navMenuOpen,
      loading,
      issueLoading,
      deletingCouponId,
      errorMessage,
      lastUpdatedAt,
      usedCouponDialogOpen,
      issueForm,
      couponStats,
      visibleCoupons,
      usedCoupons,
      loadUserCoupons,
      resetPage,
      usePreset,
      issueCoupons,
      canDeleteCoupon,
      openUsedCouponDialog,
      closeUsedCouponDialog,
      deleteCoupon,
      logoutAdmin,
      toggleNavMenu,
      closeNavMenu,
      statusLabel,
      statusClass,
      formatTime,
      money,
      avatarText,
    };
  },
}).use(vant).mount("#app");
