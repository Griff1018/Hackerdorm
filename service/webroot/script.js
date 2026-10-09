/* ============================================================
   Alex.Leads — showcase site for the Property Lead Assistant
   On submit, the form POSTs to the backend (/api/web-lead), which
   sends a REAL email with a Telegram deep link and notifies the
   agent. When no backend is reachable (e.g. opened as a local
   file), it falls back to the simulated pipeline animation.
   ============================================================ */
(function () {
  "use strict";

  var form = document.getElementById("leadForm");
  var fName = document.getElementById("name");
  var fEmail = document.getElementById("email");
  var fPhone = document.getElementById("phone");
  var fMessage = document.getElementById("message");
  var overlay = document.getElementById("overlay");
  var closeBtn = document.getElementById("closeModal");
  var tgLink = document.getElementById("tgLink");
  var tgBtn = document.getElementById("tgBtn");
  var leadName = document.getElementById("leadName");
  var leadEmail = document.getElementById("leadEmail");
  var steps = Array.prototype.slice.call(document.querySelectorAll(".pstep"));
  var submitBtn = form.querySelector('button[type="submit"]');

  function isValidEmail(v) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  }

  function resetPipeline() {
    steps.forEach(function (s) { s.classList.remove("on"); });
    tgLink.classList.remove("show");
  }

  function runPipeline() {
    resetPipeline();
    setTimeout(function () { steps[0].classList.add("on"); }, 150);   // enquiry received
    setTimeout(function () { steps[1].classList.add("on"); }, 1100);  // email sent
    setTimeout(function () { steps[2].classList.add("on"); }, 2100);  // telegram link
    setTimeout(function () {                                          // AI engaging
      steps[3].classList.add("on");
      tgLink.classList.add("show");
    }, 3100);
  }

  function openModal(name, email, tgHref) {
    leadName.textContent = name || "there";
    leadEmail.textContent = email || "you";
    if (tgBtn) {
      tgBtn.href = tgHref || "https://t.me/SandraLimRealtyBot";
      tgBtn.textContent = tgHref
        ? "Open Telegram chat with Alex"
        : "Open Telegram (demo link)";
    }
    overlay.classList.add("show");
    document.body.style.overflow = "hidden";
    runPipeline();
  }

  function closeModal() {
    overlay.classList.remove("show");
    document.body.style.overflow = "";
  }

  async function submitLead(payload, name, email) {
    submitBtn.disabled = true;
    var original = submitBtn.textContent;
    submitBtn.textContent = "Sending…";
    var res, data;
    try {
      res = await fetch("/api/web-lead", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      // Read the body either way so we can surface the server's reason.
      try { data = await res.json(); } catch (e) { data = null; }
    } catch (err) {
      // Genuine network failure: the request never completed (offline, blocked,
      // DNS failure, or a CORS preflight the browser refused). Include the raw
      // reason so it can be reported accurately instead of guessed at.
      submitBtn.disabled = false;
      submitBtn.textContent = original;
      alert("Sorry — the enquiry could not be sent.\n\n" +
            "Reason: " + (err && err.message ? err.message : err) + "\n\n" +
            "If you are on a school/office network, it may block this site. " +
            "Try a phone hotspot or mobile data.");
      return;
    }

    if (!res.ok) {
      // The server rejected it. Show the real reason instead of pretending success.
      submitBtn.disabled = false;
      submitBtn.textContent = original;
      var reason = (data && data.detail) ? data.detail : ("server error " + res.status);
      alert("Sorry — your enquiry could not be submitted.\n\n" + reason);
      return;
    }

    openModal(name, email, (data && data.telegram_link) || null);
    submitBtn.disabled = false;
    submitBtn.textContent = original;
  }

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    var name = fName.value.trim();
    var email = fEmail.value.trim();
    var phone = fPhone.value.trim();
    var intentEl = form.querySelector('input[name="intent"]:checked');
    var intent = intentEl ? intentEl.value : "Buy";
    var message = fMessage ? fMessage.value.trim() : "";

    if (!name) { alert("Please enter your name."); fName.focus(); return; }
    if (!isValidEmail(email)) { alert("Please enter a valid email."); fEmail.focus(); return; }
    if (!phone) { alert("Please enter a phone / WhatsApp number."); fPhone.focus(); return; }

    submitLead({ name: name, email: email, phone: phone, intent: intent, message: message }, name, email);
  });

  closeBtn.addEventListener("click", closeModal);
  overlay.addEventListener("click", function (e) {
    if (e.target === overlay) closeModal();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && overlay.classList.contains("show")) closeModal();
  });

  /* ---- stats counter (counts up when scrolled into view) ---- */
  var stats = document.querySelectorAll(".stat .n");
  var counted = false;
  function animateCounts() {
    if (counted) return;
    counted = true;
    stats.forEach(function (el) {
      var target = parseInt(el.getAttribute("data-count"), 10) || 0;
      var start = 0, dur = 900, t0 = null;
      function tick(ts) {
        if (!t0) t0 = ts;
        var p = Math.min((ts - t0) / dur, 1);
        el.textContent = Math.round(start + (target - start) * p);
        if (p < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  }
  if ("IntersectionObserver" in window) {
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) { if (en.isIntersecting) { animateCounts(); io.disconnect(); } });
    }, { threshold: 0.4 });
    io.observe(document.querySelector(".stats"));
  } else {
    animateCounts();
  }
})();
