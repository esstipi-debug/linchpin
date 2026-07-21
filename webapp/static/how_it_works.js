// Interactivity for GET /how-it-works: donut lens tabs, click-to-expand
// tool lists on donut segments, and expand/collapse for the grounding
// cards / certification bars / ISO accordion. Vanilla JS, no dependencies
// (matches this project's zero-external-JS-library convention).
(function () {
  "use strict";

  function bindToggle(selector) {
    document.querySelectorAll(selector).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var targetId = btn.getAttribute("data-target");
        var target = document.getElementById(targetId);
        if (!target) {
          return;
        }
        var isHidden = target.hasAttribute("hidden");
        if (isHidden) {
          target.removeAttribute("hidden");
          btn.setAttribute("aria-expanded", "true");
        } else {
          target.setAttribute("hidden", "");
          btn.setAttribute("aria-expanded", "false");
        }
      });
    });
  }

  function bindDonutLensTabs() {
    var tabs = document.querySelectorAll(".lens-tab");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var lens = tab.getAttribute("data-lens");
        tabs.forEach(function (t) {
          var isActive = t === tab;
          t.classList.toggle("active", isActive);
          t.setAttribute("aria-selected", isActive ? "true" : "false");
        });
        document.querySelectorAll(".lens-panel").forEach(function (panel) {
          panel.hidden = panel.getAttribute("data-lens") !== lens;
        });
      });
    });
  }

  function showBucket(svgId, label) {
    var listContainer = document.getElementById(svgId + "-list");
    if (!listContainer) {
      return;
    }
    listContainer.hidden = false;
    listContainer.querySelectorAll(".bucket-block").forEach(function (block) {
      block.hidden = block.getAttribute("data-bucket") !== label;
    });
  }

  function bindDonutSegmentExpand() {
    document.querySelectorAll(".donut-seg").forEach(function (seg) {
      seg.addEventListener("click", function () {
        var svg = seg.closest("svg");
        if (!svg) {
          return;
        }
        showBucket(svg.id, seg.getAttribute("data-label"));
      });
      seg.addEventListener("keydown", function (evt) {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          var svg = seg.closest("svg");
          if (svg) {
            showBucket(svg.id, seg.getAttribute("data-label"));
          }
        }
      });
    });
  }

  function bindLegendExpand() {
    document.querySelectorAll(".legend-item").forEach(function (item) {
      item.addEventListener("click", function () {
        showBucket(item.getAttribute("data-donut"), item.getAttribute("data-bucket"));
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindToggle(".card-toggle");
    bindToggle(".cert-toggle");
    bindToggle(".iso-toggle");
    bindDonutLensTabs();
    bindDonutSegmentExpand();
    bindLegendExpand();
  });
})();
