// 4th & Fury site: screenshot lightbox and the "Watch the trailer" button. No dependencies.
(function () {
  "use strict";

  // ----- Lightbox -----
  var dialog = document.getElementById("lightbox");
  var gallery = document.getElementById("gallery");
  if (dialog && gallery && typeof dialog.showModal === "function") {
    var img = document.getElementById("lightbox-img");
    var cap = document.getElementById("lightbox-cap");
    var links = Array.prototype.slice.call(gallery.querySelectorAll("a[data-shot]"));
    var shots = links.map(function (a) {
      var thumb = a.querySelector("img");
      return { id: a.getAttribute("data-shot"), href: a.getAttribute("href"), alt: thumb ? thumb.alt : "", w: thumb ? thumb.width : 16, h: thumb ? thumb.height : 9 };
    });
    var index = 0;
    var opener = null;

    function show(i) {
      index = (i + shots.length) % shots.length;
      var s = shots[index];
      img.src = s.href;
      img.alt = s.alt;
      img.width = s.w * 2;
      img.height = s.h * 2;
      cap.textContent = s.alt + "  (" + (index + 1) + " / " + shots.length + ")";
    }
    function open(id, from) {
      var i = 0;
      for (var k = 0; k < shots.length; k++) if (shots[k].id === id) i = k;
      opener = from || null;
      show(i);
      dialog.showModal();
      var close = dialog.querySelector("[data-lb=close]");
      if (close) close.focus();
    }

    links.forEach(function (a) {
      a.addEventListener("click", function (e) {
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        open(a.getAttribute("data-shot"), a);
      });
    });
    Array.prototype.forEach.call(document.querySelectorAll("button.zoom[data-shot]"), function (b) {
      b.addEventListener("click", function () { open(b.getAttribute("data-shot"), b); });
    });

    dialog.addEventListener("click", function (e) {
      var t = e.target.closest ? e.target.closest("[data-lb]") : null;
      if (t) {
        var act = t.getAttribute("data-lb");
        if (act === "close") dialog.close();
        else if (act === "prev") show(index - 1);
        else if (act === "next") show(index + 1);
        return;
      }
      // click on the dark surround closes
      if (e.target === dialog || e.target.classList.contains("lightbox__fig")) dialog.close();
    });
    dialog.addEventListener("keydown", function (e) {
      if (e.key === "ArrowLeft") { e.preventDefault(); show(index - 1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); show(index + 1); }
    });
    dialog.addEventListener("close", function () {
      if (opener && opener.focus) opener.focus();
    });
  }

  // ----- Watch the trailer: scroll to the video and start it -----
  var video = document.getElementById("trailer-video");
  Array.prototype.forEach.call(document.querySelectorAll("[data-play-trailer]"), function (a) {
    a.addEventListener("click", function (e) {
      if (!video) return;
      e.preventDefault();
      var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      document.getElementById("trailer").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
      if (history.replaceState) history.replaceState(null, "", "#trailer");
      var p = video.play();
      if (p && p.catch) p.catch(function () {});
      video.focus({ preventScroll: true });
    });
  });
})();
