// ─────────────────────────────────────────────────────────────────────────
//  Travel Agent Frontend  ·  app.js
// ─────────────────────────────────────────────────────────────────────────

let map = null;
let ws = null;
const markers = [];
let polylines = [];

// ── 持久化 key ─────────────────────────────────────────────────────────────
const STORAGE_KEY_HISTORY = "travel_chat_history";   // 消息记录
const STORAGE_KEY_MAP     = "travel_map_state";      // 地图 JSON 块（用于还原标记/行程）
const MAX_HISTORY_ITEMS   = 60;                       // 最多保留 60 条消息
let wsReconnectTimer = null;   // 重连定时器
let wsReconnectDelay = 1500;   // 初始重连间隔(ms)，指数退避
let wsSendPending = null;      // 等待重连后发送的文本

// ── Markdown renderer ─────────────────────────────────────────────────────
const md = (text) => {
  if (window.marked) {
    return marked.parse(text, { breaks: true, gfm: true });
  }
  return text.replace(/\n/g, "<br>");
};

/** 剥离后端附加的地图/天气 JSON 块，避免在对话框里显示原始 JSON */
function stripMapBlocks(text) {
  // 移除所有含 __type 的 ```json ... ``` 块
  return text.replace(/\n?```json\s*\{[^`]*"__type"[^`]*\}\s*```/g, "").trim();
}

// ── Chat log ──────────────────────────────────────────────────────────────
/** 把一条消息追加到聊天区，并持久化到 localStorage */
function appendMessage(role, text, _skipSave) {
  const log = document.getElementById("chat-log");
  const wrap = document.createElement("div");
  wrap.className = "chat-msg chat-msg-" + role;

  const label = document.createElement("span");
  label.className = "chat-msg-label";
  label.textContent = role === "user" ? "你" : "助手";

  const body = document.createElement("div");
  body.className = "chat-msg-body";
  if (role === "assistant") {
    body.innerHTML = md(stripMapBlocks(text));
  } else {
    body.textContent = text;
  }

  wrap.appendChild(label);
  wrap.appendChild(body);
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;

  if (role === "assistant") {
    extractAndPlotMapData(text);
  }

  // 持久化（重放历史时跳过，避免重复写入）
  if (!_skipSave) {
    _saveMessage(role, text);
  }
}

// ── localStorage 持久化 ───────────────────────────────────────────────────
/** 保存一条消息到 localStorage */
function _saveMessage(role, text) {
  try {
    var history = _loadHistory();
    history.push({ role: role, text: text, ts: Date.now() });
    // 超出上限时从头裁剪
    if (history.length > MAX_HISTORY_ITEMS) {
      history = history.slice(history.length - MAX_HISTORY_ITEMS);
    }
    localStorage.setItem(STORAGE_KEY_HISTORY, JSON.stringify(history));
    // 同步保存最后一条 assistant 地图块（供地图还原用）
    if (role === "assistant") {
      _saveMapBlocks(text);
    }
  } catch(e) { /* 存储配额满等极端情况，静默忽略 */ }
}

/** 读取历史消息数组 */
function _loadHistory() {
  try {
    var raw = localStorage.getItem(STORAGE_KEY_HISTORY);
    return raw ? JSON.parse(raw) : [];
  } catch(e) { return []; }
}

/** 把所有 assistant 消息中的地图 JSON 块累积保存（供还原地图用）*/
function _saveMapBlocks(text) {
  try {
    var existing = [];
    try { existing = JSON.parse(localStorage.getItem(STORAGE_KEY_MAP) || "[]"); } catch(_) {}
    // 提取当前消息中的 JSON 块
    var re = /```json\s*([\s\S]*?)```/g, m;
    while ((m = re.exec(text)) !== null) {
      try {
        var obj = JSON.parse(m[1].trim());
        if (obj.__type) existing.push(obj);
      } catch(_) {}
    }
    // 只保留最近 20 个地图块
    if (existing.length > 20) existing = existing.slice(existing.length - 20);
    localStorage.setItem(STORAGE_KEY_MAP, JSON.stringify(existing));
  } catch(e) {}
}

/** 清除所有持久化数据（清除对话时调用）*/
function clearHistory() {
  localStorage.removeItem(STORAGE_KEY_HISTORY);
  localStorage.removeItem(STORAGE_KEY_MAP);
  document.getElementById("chat-log").innerHTML = "";
  clearMapMarkers();
  document.getElementById("weather-bar").style.display = "none";
  document.getElementById("side-panel").style.display = "none";
  document.getElementById("toggle-side-btn").style.display = "none";
  sidePanelData = { itinerary: null, hotel: [], restaurant: [] };
}

/** 页面加载时还原历史对话和地图 */
function _restoreHistory() {
  var history = _loadHistory();
  if (history.length === 0) return;

  // 还原消息（_skipSave=true 避免重复写入）
  history.forEach(function(item) {
    appendMessage(item.role, item.text, true);
  });

  // 地图块：直接重放最新保存的那批 JSON 块
  try {
    var blocks = JSON.parse(localStorage.getItem(STORAGE_KEY_MAP) || "[]");
    blocks.forEach(function(obj) {
      // 构造带 ```json ``` 包装的字符串，复用已有逻辑
      var fakeText = "\n```json\n" + JSON.stringify(obj) + "\n```";
      extractAndPlotMapData(fakeText);
    });
  } catch(e) {}
}

function showTyping() {
  const log = document.getElementById("chat-log");
  const el = document.createElement("div");
  el.id = "typing-indicator";
  el.className = "chat-msg chat-msg-assistant typing";
  el.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span>';
  log.appendChild(el);
  log.scrollTop = log.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

// ── WebSocket ─────────────────────────────────────────────────────────────
function initWebSocket() {
  if (wsReconnectTimer) { clearTimeout(wsReconnectTimer); wsReconnectTimer = null; }
  const proto = window.location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(proto + "://" + window.location.host + "/ws/chat");

  ws.onopen = () => {
    console.log("[WS] connected");
    wsReconnectDelay = 1500;   // 重置退避
    // 若有待发送消息，补发
    if (wsSendPending) {
      const text = wsSendPending; wsSendPending = null;
      appendMessage("user", text);
      showTyping();
      ws.send(text);
    }
  };

  ws.onmessage = (event) => {
    removeTyping();
    appendMessage("assistant", event.data);
  };

  ws.onerror = (err) => {
    console.error("[WS] error", err);
    removeTyping();
  };

  ws.onclose = (ev) => {
    removeTyping();
    // 非主动关闭（code 1000/1001）才重连
    if (ev.code !== 1000 && ev.code !== 1001) {
      appendMessage("assistant", `⚠️ 连接中断（code ${ev.code}），${(wsReconnectDelay/1000).toFixed(1)}s 后自动重连…`);
      wsReconnectTimer = setTimeout(() => {
        wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
        initWebSocket();
      }, wsReconnectDelay);
    } else {
      appendMessage("assistant", "连接已关闭。");
    }
  };
}

// ── Map (AMap JS API v2.0) ───────────────────────────────────────────
function initMap() {
  // 确保 #map 充满父容器高度（解决 flex 嵌套导致高度为 0 的问题）
  var mapEl = document.getElementById("map");
  var container = mapEl && mapEl.parentElement;
  function setMapSize() {
    if (!container) return;
    var h = container.offsetHeight;
    if (h > 0) {
      mapEl.style.height = h + "px";
    }
  }
  setMapSize();
  if (window.ResizeObserver && container) {
    new ResizeObserver(function() {
      setMapSize();
      if (map) { try { map.resize(); } catch(e) {} }
    }).observe(container);
  }

  try {
    map = new AMap.Map("map", {
      zoom: 11,
      center: [104.0657, 30.6596],
    });
    AMap.plugin(["AMap.ToolBar", "AMap.Scale"], function() {
      map.addControl(new AMap.ToolBar({ position: "RB" }));
      map.addControl(new AMap.Scale());
    });
    setTimeout(function() { setMapSize(); try { map.resize(); } catch(e) {} }, 200);
  } catch (e) {
    console.warn("[Map] AMap init failed:", e);
  }
}

const MARKER_ICONS = {
  poi:        { label: "📍" },
  hotel:      { label: "🏨" },
  restaurant: { label: "🍜" },
  route:      { label: "🚗" },
};

function addMarker(lng, lat, title, type, extra) {
  type = type || "poi";
  extra = extra || {};
  if (!map) return;
  try {
    const icon = MARKER_ICONS[type] || MARKER_ICONS.poi;
    const marker = new AMap.Marker({
      position: new AMap.LngLat(lng, lat),
      title: title,
      label: {
        content: '<div class="map-label map-label-' + type + '">' + icon.label + " " + title + "</div>",
        direction: "top",
      },
    });
    marker.on("click", () => showInfoPanel(title, type, lng, lat, extra));
    marker.setMap(map);
    markers.push(marker);
  } catch (e) {
    console.warn("[Map] addMarker failed:", e);
  }
}

function drawPolyline(coords) {
  if (!map || !coords || coords.length < 2) return;
  try {
    var path = coords.map(function(c) { return new AMap.LngLat(c[0], c[1]); });
    var line = new AMap.Polyline({
      path: path,
      strokeColor: "#722ed1",
      strokeWeight: 4,
      strokeOpacity: 0.85,
      strokeStyle: "dashed",
    });
    line.setMap(map);
    polylines.push(line);
  } catch (e) { console.warn("[Map] drawPolyline failed:", e); }
}

function clearMapMarkers() {
  markers.forEach(function(m) { m.setMap(null); });
  markers.length = 0;
  polylines.forEach(function(p) { p.setMap(null); });
  polylines = [];
}

function fitMapBounds() {
  if (!map || markers.length === 0) return;
  try { map.setFitView(markers); } catch (e) { console.warn("[Map] fitView failed:", e); }
}

// ── Info panel ─────────────────────────────────────────────────────────────
function showInfoPanel(title, type, lng, lat, extra) {
  extra = extra || {};
  var panel = document.getElementById("info-panel");
  var titleEl = document.getElementById("info-panel-title");
  var body = document.getElementById("info-panel-body");
  var icon = (MARKER_ICONS[type] || MARKER_ICONS.poi).label;
  titleEl.textContent = icon + " " + title;

  var rows = "";

  // 图片轮播
  var photos = extra.photos || [];
  if (photos.length > 0) {
    rows += '<div class="poi-photos">';
    photos.forEach(function(url) {
      rows += '<img class="poi-photo" src="' + url + '" alt="' + title + '" loading="lazy" ' +
              'onerror="this.style.display=\'none\'">';
    });
    rows += '</div>';
  }

  if (extra.address) rows += "<p><strong>📍 地址：</strong>" + extra.address + "</p>";
  if (extra.tel)     rows += "<p><strong>📞 电话：</strong>" + extra.tel + "</p>";
  if (extra.rating)  rows += "<p><strong>⭐ 评分：</strong>" + extra.rating + "</p>";
  if (extra.cost)    rows += "<p><strong>💰 人均：</strong>¥" + extra.cost + "</p>";
  rows += "<p><strong>🌐 坐标：</strong>" + lat.toFixed(5) + ", " + lng.toFixed(5) + "</p>";
  rows +=
    '<a href="https://uri.amap.com/marker?position=' + lng + "," + lat +
    "&name=" + encodeURIComponent(title) + "&src=travel-agent&coordinate=gaode&callnative=1" +
    '" target="_blank" class="amap-nav-link">📱 高德导航</a>';

  body.innerHTML = rows;
  panel.style.display = "flex";

  // 地图飞到该点并放大
  if (map) {
    try { map.setZoomAndCenter(15, [lng, lat]); } catch (e) {}
  }
}

// ── Weather bar ───────────────────────────────────────────────────────────
const WEATHER_ICONS = {
  "晴": "☀️", "多云": "⛅", "阴": "☁️",
  "小雨": "🌧️", "中雨": "🌧️", "大雨": "🌧️", "暴雨": "⛈️",
  "雷阵雨": "⛈️", "小雪": "🌨️", "中雪": "🌨️", "大雪": "❄️",
  "雾": "🌫️", "霾": "😷", "沙尘暴": "🌪️",
};

function getWeatherIcon(desc) {
  if (!desc) return "🌡️";
  for (const key in WEATHER_ICONS) {
    if (desc.indexOf(key) !== -1) return WEATHER_ICONS[key];
  }
  return "🌡️";
}

function renderWeatherBar(city, days) {
  const bar = document.getElementById("weather-bar");
  if (!bar || !days || days.length === 0) return;

  const weekMap = ["", "一", "二", "三", "四", "五", "六", "日"];
  let html = '<div class="weather-city">📍 ' + city + ' 天气</div>';
  days.forEach(function(d) {
    const icon = getWeatherIcon(d.day_weather || "");
    const week = weekMap[parseInt(d.week, 10)] || d.week;
    html +=
      '<div class="weather-day">' +
        '<span class="weather-date">' + (d.date || "").slice(5) + ' 周' + week + '</span>' +
        '<span class="weather-icon">' + icon + '</span>' +
        '<span class="weather-desc">' + (d.day_weather || "--") + '</span>' +
        '<span class="weather-temp">' + (d.night_temp || "--") + '~' + (d.day_temp || "--") + '°C</span>' +
        '<span class="weather-wind">' + (d.wind_direction || "") + ' ' + (d.wind_power || "") + '级</span>' +
      '</div>';
  });
  bar.innerHTML = html;
  bar.style.display = "flex";
}

// ── Extract & plot map data from LLM replies ──────────────────────────────
function extractAndPlotMapData(text) {
  const jsonBlockRe = /```json\s*([\s\S]*?)```/g;
  let match;
  const newMarkers = [];

  while ((match = jsonBlockRe.exec(text)) !== null) {
    try {
      const obj = JSON.parse(match[1].trim());

      if (obj.__type === "pois" && Array.isArray(obj.items)) {
        const hotelItems = [];
        const restaurantItems = [];
        obj.items.forEach(function(item) {
          const lng = parseFloat(item.longitude);
          const lat = parseFloat(item.latitude);
          if (!isNaN(lng) && !isNaN(lat)) {
            addMarker(lng, lat, item.name || "地点", item.type || "poi", {
              address: item.address || "",
              tel:     item.tel     || "",
              rating:  item.rating  || "",
              cost:    item.cost    || "",
              photos:  item.photos  || [],
              cuisine: item.cuisine || "",
            });
            newMarkers.push([lng, lat]);
            // 分类收集用于侧边面板
            if (item.type === "hotel") hotelItems.push(item);
            else if (item.type === "restaurant") restaurantItems.push(item);
          }
        });
        if (hotelItems.length > 0) updateSidePanelFromPois(hotelItems, "hotel");
        if (restaurantItems.length > 0) updateSidePanelFromPois(restaurantItems, "restaurant");
      }

      if (obj.__type === "route" && Array.isArray(obj.polyline)) {
        drawPolyline(obj.polyline);
        if (obj.polyline.length > 0) {
          addMarker(obj.polyline[0][0], obj.polyline[0][1],
            obj.origin || "出发", "route",
            { address: obj.origin || "" });
          const last = obj.polyline[obj.polyline.length - 1];
          addMarker(last[0], last[1],
            obj.destination || "到达", "route",
            { address: obj.destination || "",
              address2: obj.distance_km ? obj.distance_km + " km / " + obj.duration_min + " 分钟" : "" });
        }
        // 把路线全部坐标也加入 fitBounds 范围
        obj.polyline.forEach(function(c) { newMarkers.push([c[0], c[1]]); });
      }

      if (obj.__type === "weather" && Array.isArray(obj.days)) {
        renderWeatherBar(obj.city || "", obj.days);
      }

      if (obj.__type === "itinerary" && Array.isArray(obj.days)) {
        renderItineraryOnMap(obj);
      }
    } catch (_) {}
  }

  // 兼容：回复正文里直接出现的坐标对 [lng, lat]
  const inlineRe = /\[(\s*-?\d+\.\d+\s*),(\s*-?\d+\.\d+\s*)\]/g;
  while ((match = inlineRe.exec(text)) !== null) {
    const lng = parseFloat(match[1]);
    const lat = parseFloat(match[2]);
    if (lng > 73 && lng < 135 && lat > 3 && lat < 54) {
      addMarker(lng, lat, "📍 " + lng.toFixed(4) + "," + lat.toFixed(4), "poi");
      newMarkers.push([lng, lat]);
    }
  }

  if (newMarkers.length > 0) {
    setTimeout(fitMapBounds, 300);
  }
}

// ── Global state for itinerary & side panel ───────────────────────────────
const DAY_COLORS = ["#4f46e5","#0891b2","#059669","#d97706","#dc2626","#7c3aed","#0284c7"];
let itineraryLines = [];   // 行程连线（每日分组）
let sidePanelData  = { itinerary: null, hotel: [], restaurant: [] };
let activeSideTab  = "itinerary";

// ── 编号 marker（行程专用）──────────────────────────────────────────────────
function addNumberedMarker(lng, lat, num, label, color, extra) {
  if (!map) return null;
  try {
    var marker = new AMap.Marker({
      position: new AMap.LngLat(lng, lat),
      content: '<div class="itinerary-pin" style="background:' + color + '">' + num + '</div>',
      anchor: "bottom-center",
      title: label,
    });
    marker.on("click", function() { showInfoPanel(label, extra.type || "poi", lng, lat, extra); });
    marker.setMap(map);
    markers.push(marker);
    return marker;
  } catch(e) { console.warn("[Map] addNumberedMarker failed:", e); return null; }
}

// ── 行程连线──────────────────────────────────────────────────────────────
function drawItineraryLines(spots, color) {
  if (!map || spots.length < 2) return;
  try {
    var path = spots.map(function(s) { return new AMap.LngLat(s.longitude, s.latitude); });
    var line = new AMap.Polyline({
      path: path,
      strokeColor: color,
      strokeWeight: 2,
      strokeOpacity: 0.7,
      strokeStyle: "dashed",
      lineJoin: "round",
    });
    line.setMap(map);
    itineraryLines.push(line);
    polylines.push(line);
  } catch(e) { console.warn("[Map] drawItineraryLines failed:", e); }
}

// ── 渲染行程到地图 ──────────────────────────────────────────────────────
function renderItineraryOnMap(obj) {
  // 清除旧行程线
  itineraryLines.forEach(function(l) { l.setMap(null); });
  itineraryLines = [];

  var allCoords = [];
  (obj.days || []).forEach(function(day, di) {
    var color = DAY_COLORS[di % DAY_COLORS.length];
    var spots = day.spots || [];

    // 编号景点标记
    spots.forEach(function(s, si) {
      addNumberedMarker(s.longitude, s.latitude, si + 1, s.name, color, s);
      allCoords.push([s.longitude, s.latitude]);
    });

    // 日内连线
    drawItineraryLines(spots, color);

    // 酒店标记
    if (day.hotel) {
      var h = day.hotel;
      addMarker(h.longitude, h.latitude, h.name, "hotel", h);
      allCoords.push([h.longitude, h.latitude]);
    }

    // 餐厅标记
    (day.meals || []).forEach(function(m) {
      addMarker(m.longitude, m.latitude, m.name, "restaurant", m);
      allCoords.push([m.longitude, m.latitude]);
    });
  });

  if (allCoords.length > 0) {
    setTimeout(fitMapBounds, 300);
  }

  // 填充侧边面板数据（按名称去重，避免同一家酒店因每天都分配而重复）
  sidePanelData.itinerary = obj;
  sidePanelData.hotel = [];
  sidePanelData.restaurant = [];
  var _seenHotels = {};
  var _seenMeals = {};
  (obj.days || []).forEach(function(day) {
    if (day.hotel && !_seenHotels[day.hotel.name]) {
      _seenHotels[day.hotel.name] = true;
      sidePanelData.hotel.push(day.hotel);
    }
    (day.meals || []).forEach(function(m) {
      if (!_seenMeals[m.name]) {
        _seenMeals[m.name] = true;
        sidePanelData.restaurant.push(m);
      }
    });
  });

  // 显示侧边面板
  document.getElementById("side-panel").style.display = "flex";
  document.getElementById("toggle-side-btn").style.display = "";
  renderSidePanel("itinerary");
}

// ── 侧边面板 ──────────────────────────────────────────────────────────────
function toggleSidePanel() {
  var p = document.getElementById("side-panel");
  p.style.display = p.style.display === "none" ? "flex" : "none";
}

function renderSidePanel(tab) {
  activeSideTab = tab;
  // 更新 tab 激活状态
  document.querySelectorAll(".side-tab").forEach(function(btn) {
    btn.classList.toggle("active", btn.dataset.tab === tab);
  });

  var body = document.getElementById("side-panel-body");
  if (!body) return;

  if (tab === "itinerary" && sidePanelData.itinerary) {
    body.innerHTML = renderItineraryCards(sidePanelData.itinerary);
  } else if (tab === "hotel") {
    body.innerHTML = renderPoiCards(sidePanelData.hotel, "hotel");
  } else if (tab === "restaurant") {
    body.innerHTML = renderPoiCards(sidePanelData.restaurant, "restaurant");
  } else {
    body.innerHTML = "<p class='side-empty'>暂无数据</p>";
  }
}

// 行程卡片（按天展示）
function renderItineraryCards(obj) {
  var html = "";
  if (obj.title) html += '<div class="itinerary-title">' + obj.title + '</div>';
  (obj.days || []).forEach(function(day, di) {
    var color = DAY_COLORS[di % DAY_COLORS.length];
    html += '<div class="day-block">';
    html += '<div class="day-label" style="border-left:3px solid ' + color + '">' + day.label + '</div>';
    (day.spots || []).forEach(function(s, si) {
      html += _poiCardHtml(s, si + 1, color);
    });
    if (day.hotel) {
      html += '<div class="day-sub-label">🏨 住宿</div>' + _poiCardHtml(day.hotel, null, "#0891b2");
    }
    if ((day.meals || []).length > 0) {
      html += '<div class="day-sub-label">🍜 餐厅</div>';
      day.meals.forEach(function(m) { html += _poiCardHtml(m, null, "#059669"); });
    }
    html += '</div>';
  });
  return html || "<p class='side-empty'>暂无行程数据</p>";
}

// POI 列表卡片（酒店/餐厅）
function renderPoiCards(list, type) {
  if (!list || list.length === 0) return "<p class='side-empty'>暂无数据</p>";
  return list.map(function(item) { return _poiCardHtml(item, null, type === "hotel" ? "#0891b2" : "#059669"); }).join("");
}

function _poiCardHtml(item, num, color) {
  var photo = (item.photos && item.photos[0]) ? item.photos[0] : "";
  var stars = "";
  if (item.rating && parseFloat(item.rating) > 0) {
    stars = "⭐ " + item.rating;
  }
  var cost = item.cost ? "💰 ¥" + item.cost : "";
  var cuisine = item.cuisine ? "🍽️ " + item.cuisine : "";
  var note = item.note ? '<span class="poi-card-note">' + item.note + '</span>' : "";
  var numBadge = num !== null && num !== undefined
    ? '<span class="poi-card-num" style="background:' + color + '">' + num + '</span>' : "";

  // 用 data-* 属性存储 POI 数据，避免 onclick 字符串中的引号冲突
  var dataJson = JSON.stringify(item).replace(/'/g, "&#39;");

  return '<div class="poi-card" data-poi=\'' + dataJson + '\' onclick="_onPoiCardClick(this)">' +
    (photo ? '<img class="poi-card-img" src="' + photo + '" onerror="this.style.display=\'none\'" loading="lazy">' : "") +
    '<div class="poi-card-body">' +
      numBadge +
      '<div class="poi-card-name">' + item.name + '</div>' +
      (stars || cost ? '<div class="poi-card-meta">' + stars + (stars && cost ? " · " : "") + cost + cuisine + '</div>' : "") +
      (item.address ? '<div class="poi-card-addr">📍 ' + item.address + '</div>' : "") +
      note +
    '</div>' +
  '</div>';
}

// poi-card 点击处理（从 data-poi 属性解析 POI 数据）
function _onPoiCardClick(el) {
  try {
    var item = JSON.parse(el.getAttribute("data-poi"));
    focusPoi(item.longitude, item.latitude, item.name, item.type || "poi", item);
  } catch(e) { console.warn("[_onPoiCardClick]", e); }
}

// 点击卡片：地图跳转 + 打开 info-panel
function focusPoi(lng, lat, name, type, extra) {
  if (map) {
    try { map.setZoomAndCenter(15, [lng, lat]); } catch(e) {}
  }
  showInfoPanel(name, type, lng, lat, extra);
}

// 侧边面板 tab 绑定（在 bindUI 里调用）
function bindSideTabs() {
  document.querySelectorAll(".side-tab").forEach(function(btn) {
    btn.addEventListener("click", function() { renderSidePanel(btn.dataset.tab); });
  });
}

// 有酒店/餐厅数据时自动填充侧边面板（不是 itinerary 的情况）
function updateSidePanelFromPois(items, type) {
  if (!items || items.length === 0) return;
  if (type === "hotel") {
    var existing = new Set(sidePanelData.hotel.map(function(h) { return h.name; }));
    items.forEach(function(h) { if (!existing.has(h.name)) { existing.add(h.name); sidePanelData.hotel.push(h); } });
  } else if (type === "restaurant") {
    var existing = new Set(sidePanelData.restaurant.map(function(r) { return r.name; }));
    items.forEach(function(r) { if (!existing.has(r.name)) { existing.add(r.name); sidePanelData.restaurant.push(r); } });
  }
  if (sidePanelData.hotel.length > 0 || sidePanelData.restaurant.length > 0) {
    document.getElementById("side-panel").style.display = "flex";
    document.getElementById("toggle-side-btn").style.display = "";
    // 如果当前激活 tab 是对应类型，刷新
    if (activeSideTab === type) renderSidePanel(type);
  }
}

// ── UI bindings ───────────────────────────────────────────────────────────
function bindUI() {
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("send-btn");

  const send = () => {
    const text = input.value.trim();
    if (!text) return;

    if (!ws || ws.readyState === WebSocket.CLOSED || ws.readyState === WebSocket.CLOSING) {
      // WS 已断开，暂存消息，触发重连，连接成功后自动发送
      wsSendPending = text;
      input.value = "";
      appendMessage("assistant", "⏳ 正在重新连接服务器，稍后自动发送…");
      initWebSocket();
      return;
    }

    if (ws.readyState === WebSocket.CONNECTING) {
      // 正在握手，先暂存
      wsSendPending = text;
      input.value = "";
      appendMessage("assistant", "⏳ 连接中，稍后自动发送…");
      return;
    }

    appendMessage("user", text);
    showTyping();
    ws.send(text);
    input.value = "";
  };

  sendBtn.addEventListener("click", send);
  input.addEventListener("keyup", function(e) {
    if (e.key === "Enter") send();
  });
}

// ── 导出 PDF ──────────────────────────────────────────────────────────────
/**
 * 将当前 sidePanelData 发到 /api/export-pdf，
 * 后端返回 PDF（或降级 HTML），触发浏览器下载。
 */
function exportItineraryPDF() {
  if (!sidePanelData.itinerary && !sidePanelData.hotel.length && !sidePanelData.restaurant.length) {
    alert('还没有行程数据，请先让助手规划一条旅程 🗺️');
    return;
  }
  var btn = document.getElementById('export-pdf-btn');
  if (btn) { btn.textContent = '⏳ 生成中…'; btn.disabled = true; }

  fetch('/api/export-pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      itinerary:  sidePanelData.itinerary  || {},
      hotel:      sidePanelData.hotel      || [],
      restaurant: sidePanelData.restaurant || [],
    }),
  })
  .then(function(res) {
    if (!res.ok) return res.text().then(function(t) { throw new Error(t); });
    return res.blob();
  })
  .then(function(blob) {
    // 在新标签页打开 HTML，页面自动触发 window.print()
    // 用户在打印对话框选"另存为 PDF"即可保存
    var url = URL.createObjectURL(blob);
    var win = window.open(url, '_blank');
    if (!win) {
      // 弹窗被拦截时降级为下载 HTML
      var a = document.createElement('a');
      var city = (sidePanelData.itinerary || {}).city || '旅行';
      a.href = url;
      a.download = city + '旅行攻略.html';
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
    setTimeout(function() { URL.revokeObjectURL(url); }, 30000);
  })
  .catch(function(err) {
    console.error('[exportPDF]', err);
    alert('导出失败：' + err.message);
  })
  .finally(function() {
    if (btn) { btn.textContent = '📥 导出 PDF'; btn.disabled = false; }
  });
}

// ── Bootstrap ─────────────────────────────────────────────────────────────
// 高德 JS API 通过 <script> 同步加载，DOMContentLoaded 时已可直接使用 AMap
window.addEventListener("DOMContentLoaded", function() {
  initMap();
  initWebSocket();
  bindUI();
  bindSideTabs();
  _restoreHistory();
});

