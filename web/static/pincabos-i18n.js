/*
 * PinCabOs-File created by Karots Sugarpie
 * Hidden Google Translate widget controller - multi-language Europe
 *
 * Dependencies / requisites:
 * - Browser internet access to https://translate.google.com
 * - Existing PinCabOS language select: #pincabos_language_select
 * - Existing menu calls: window.setPinCabOsLanguage('<code>')
 *
 * Supported languages:
 * - fr: Français
 * - en: English
 * - es: Español
 * - it: Italiano
 * - de: Deutsch
 * - nl: Nederlands
 *
 * Created by Karots Sugarpie
 */

(function () {
  "use strict";

  const STORAGE_KEY = "pincabos_lang";
  const GOOGLE_SCRIPT_ID = "pincabos-google-translate-script";
  const GOOGLE_ELEMENT_ID = "google_translate_element";
  const HIDE_STYLE_ID = "pincabos-google-translate-hide-style";

  const SUPPORTED_LANGS = {
    fr: "Français",
    en: "English",
    es: "Español",
    it: "Italiano",
    de: "Deutsch",
    nl: "Nederlands"
  };

  const INCLUDED_LANGUAGES = Object.keys(SUPPORTED_LANGS).join(",");

  function normalizeLang(lang) {
    return Object.prototype.hasOwnProperty.call(SUPPORTED_LANGS, lang) ? lang : "fr";
  }

  function injectHideStyle() {
    if (document.getElementById(HIDE_STYLE_ID)) return;

    const style = document.createElement("style");
    style.id = HIDE_STYLE_ID;
    style.textContent = `
      html {
        top: 0 !important;
      }

      body {
        top: 0 !important;
        position: static !important;
        min-height: 100vh !important;
      }

      .goog-te-banner-frame,
      .goog-te-banner-frame.skiptranslate,
      iframe.goog-te-banner-frame,
      iframe.goog-te-menu-frame,
      .skiptranslate iframe,
      body > .skiptranslate,
      .goog-logo-link,
      .goog-te-gadget span,
      .goog-te-balloon-frame {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        width: 0 !important;
        height: 0 !important;
        max-width: 0 !important;
        max-height: 0 !important;
        overflow: hidden !important;
        pointer-events: none !important;
      }

      #${GOOGLE_ELEMENT_ID} {
        display: block !important;
        position: fixed !important;
        left: -99999px !important;
        top: -99999px !important;
        width: 1px !important;
        height: 1px !important;
        opacity: 0 !important;
        overflow: hidden !important;
        pointer-events: none !important;
        z-index: -1 !important;
      }

      .goog-te-combo {
        position: absolute !important;
        left: -99999px !important;
        top: -99999px !important;
        width: 1px !important;
        height: 1px !important;
        opacity: 0 !important;
      }
    `;
    document.head.appendChild(style);
  }

  function ensureGoogleElement() {
    let el = document.getElementById(GOOGLE_ELEMENT_ID);
    if (!el) {
      el = document.createElement("div");
      el.id = GOOGLE_ELEMENT_ID;
      el.setAttribute("aria-hidden", "true");
      document.body.appendChild(el);
    }
    return el;
  }

  function setHtmlLang(lang) {
    document.documentElement.setAttribute("lang", normalizeLang(lang));
  }

  function setCookie(name, value) {
    const oneYear = 60 * 60 * 24 * 365;
    document.cookie = `${name}=${value}; path=/; max-age=${oneYear}`;

    try {
      const host = window.location.hostname;
      if (host && host.includes(".")) {
        document.cookie = `${name}=${value}; path=/; domain=.${host}; max-age=${oneYear}`;
      }
    } catch (e) {}
  }

  function clearGoogleTranslateCookie() {
    document.cookie = "googtrans=; path=/; max-age=0";

    try {
      const host = window.location.hostname;
      if (host && host.includes(".")) {
        document.cookie = `googtrans=; path=/; domain=.${host}; max-age=0`;
      }
    } catch (e) {}
  }

  function killGoogleBannerOffset() {
    try {
      document.documentElement.style.top = "0px";
      document.body.style.top = "0px";
      document.body.style.position = "static";
    } catch (e) {}

    document.querySelectorAll(
      ".goog-te-banner-frame, iframe.goog-te-banner-frame, iframe.goog-te-menu-frame, .goog-te-balloon-frame"
    ).forEach(function (el) {
      try {
        el.style.display = "none";
        el.style.visibility = "hidden";
        el.style.opacity = "0";
        el.style.width = "0";
        el.style.height = "0";
      } catch (e) {}
    });
  }

  function findGoogleCombo() {
    return document.querySelector("select.goog-te-combo");
  }

  function dispatchChange(el) {
    if (!el) return;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  window.googleTranslateElementInit = function () {
    injectHideStyle();
    ensureGoogleElement();

    try {
      new google.translate.TranslateElement(
        {
          pageLanguage: "fr",
          includedLanguages: INCLUDED_LANGUAGES,
          autoDisplay: false,
          layout: google.translate.TranslateElement.InlineLayout.SIMPLE
        },
        GOOGLE_ELEMENT_ID
      );
    } catch (e) {}

    const saved = normalizeLang(localStorage.getItem(STORAGE_KEY) || "fr");
    setTimeout(function () {
      window.setPinCabOsLanguage(saved);
    }, 800);
  };

  function loadGoogleWidget() {
    injectHideStyle();
    ensureGoogleElement();

    if (document.getElementById(GOOGLE_SCRIPT_ID)) return;

    const script = document.createElement("script");
    script.id = GOOGLE_SCRIPT_ID;
    script.src = "https://translate.google.com/translate_a/element.js?cb=googleTranslateElementInit";
    script.async = true;
    document.head.appendChild(script);
  }


  function reloadForLanguageChange() {
    try {
      const url = new URL(window.location.href);
      url.searchParams.set("_pincabos_lang_reload", Date.now().toString());
      window.location.replace(url.toString());
    } catch (e) {
      window.location.reload();
    }
  }

  function shouldReloadForLanguage(target) {
    const current = normalizeLang(localStorage.getItem(STORAGE_KEY) || "fr");
    return current !== target;
  }

  function applyGoogleLanguage(lang) {
    const target = normalizeLang(lang);
    const combo = findGoogleCombo();

    localStorage.setItem(STORAGE_KEY, target);
    setHtmlLang(target);

    if (target === "fr") {
      clearGoogleTranslateCookie();

      if (combo) {
        combo.value = "";
        dispatchChange(combo);
      }

      setTimeout(killGoogleBannerOffset, 150);
      setTimeout(killGoogleBannerOffset, 600);
      return;
    }

    setCookie("googtrans", `/fr/${target}`);

    if (combo) {
      combo.value = target;
      dispatchChange(combo);
    } else {
      loadGoogleWidget();
    }

    setTimeout(killGoogleBannerOffset, 150);
    setTimeout(killGoogleBannerOffset, 600);
    setTimeout(killGoogleBannerOffset, 1400);
  }

  window.setPinCabOsLanguage = function (lang) {
    const safe = normalizeLang(lang);

    const select = document.getElementById("pincabos_language_select");
    if (select) {
      select.value = safe;
    }

    const mustReload = shouldReloadForLanguage(safe);
    applyGoogleLanguage(safe);

    if (mustReload) {
      setTimeout(reloadForLanguageChange, 250);
    }
  };

  function updateNativeSelectOptions() {
    const select = document.getElementById("pincabos_language_select");
    if (!select) return;

    const existingValues = Array.from(select.options || []).map(function (opt) {
      return opt.value;
    });

    Object.keys(SUPPORTED_LANGS).forEach(function (code) {
      if (existingValues.includes(code)) return;

      const option = document.createElement("option");
      option.value = code;
      option.textContent = SUPPORTED_LANGS[code];
      select.appendChild(option);
    });
  }

  function boot() {
    injectHideStyle();
    ensureGoogleElement();
    updateNativeSelectOptions();

    const saved = normalizeLang(localStorage.getItem(STORAGE_KEY) || "fr");
    setHtmlLang(saved);

    const select = document.getElementById("pincabos_language_select");
    if (select) {
      select.value = saved;
      select.onchange = function () {
        window.setPinCabOsLanguage(normalizeLang(this.value));
      };
    }

    loadGoogleWidget();
    setInterval(killGoogleBannerOffset, 1000);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
