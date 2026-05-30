(function () {
  const STORAGE_KEY = "pincabos_lang";
  const frToEn = {
    "Langue :": "Language:",
    "Français": "French",
    "English": "English",
    "Tableau de bord": "Dashboard",
    "Mises à jour": "Updates",
    "Réseau": "Network",
    "DOF": "DOF",
    "GPU / Écrans": "GPU / Screens",
    "FullDMD": "FullDMD",
    "Console Linux": "Linux Console",
    "À propos": "About",
    "Ouvrir le gestionnaire VPinFE": "Open VPinFE Manager",
    "Afficher PinCabOs sur le pincab :": "Show PinCabOs on the pincab:",
    "Playfield": "Playfield",
    "Backglass": "Backglass",
    "Système": "System",
    "Utilisation": "Usage",
    "Mémoire": "Memory",
    "Disques": "Disks",
    "Services": "Services",
    "Chemins essentiels": "Essential paths",
    "Versions": "Versions",
    "État": "Status",
    "Contrôle": "Control",
    "Activer": "Enable",
    "Désactiver": "Disable",
    "Relancer": "Restart",
    "Configuration réseau": "Network configuration",
    "État réseau": "Network status",
    "Mode réseau": "Network mode",
    "Interface principale détectée :": "Main interface detected:",
    "Mode détecté :": "Detected mode:",
    "IPv4 actuelle :": "Current IPv4:",
    "Passerelle :": "Gateway:",
    "DNS :": "DNS:",
    "DHCP automatique": "Automatic DHCP",
    "IP fixe": "Static IP",
    "Adresse IP/CIDR": "IP address/CIDR",
    "Appliquer la configuration réseau": "Apply network configuration",
    "WiFi — joindre un réseau": "WiFi — join a network",
    "WiFi — Hotspot PinCabOs": "WiFi — PinCabOs Hotspot",
    "Réseau WiFi": "WiFi network",
    "Mot de passe WiFi": "WiFi password",
    "Joindre le réseau WiFi": "Join WiFi network",
    "Rafraîchir scan WiFi": "Refresh WiFi scan",
    "Activer le hotspot": "Enable hotspot",
    "Désactiver le hotspot": "Disable hotspot",
    "Détails réseau complets": "Full network details",
    "Calibration FullDMD": "FullDMD calibration",
    "Déplace et étire le rectangle pour représenter la zone visible du FullDMD.": "Move and resize the rectangle to represent the visible FullDMD area.",
    "Écran FullDMD / DMD Screen ID": "FullDMD / DMD screen ID",
    "Largeur": "Width",
    "Hauteur": "Height",
    "Ouvrir calibration sur le pincab": "Open calibration on the pincab",
    "Appliquer FullDMD": "Apply FullDMD",
    "Sauvegarder FullDMD": "Save FullDMD",
    "Rafraîchir": "Refresh",
    "Terminal Web PinCabOs.": "PinCabOs Web Terminal.",
    "Changer le mot de passe root": "Change root password",
    "Ouvrir la console dans un nouvel onglet": "Open console in a new tab",
    "À propos de PinCabOs": "About PinCabOs",
    "Ce que PinCabOs fait actuellement": "What PinCabOs currently does",
    "Objectif du projet": "Project goal",
    "Backup et restauration — vision future": "Backup and restore — future vision",
    "Cloud et mises à jour": "Cloud and updates",
    "Soutenir PinCabOs": "Support PinCabOs",
    "Auteur": "Author"
  };
  function normalizeText(s) {
    return (s || "").replace(/\s+/g, " ").trim();
  }
  function saveOriginalPageHtml() {
    if (!document.body.dataset.pincabosOriginalHtml) {
      document.body.dataset.pincabosOriginalHtml = document.body.innerHTML;
    }
  }
  function restoreOriginalPageHtml() {
    if (document.body.dataset.pincabosOriginalHtml) {
      const lang = localStorage.getItem(STORAGE_KEY) || "fr";
      document.body.innerHTML = document.body.dataset.pincabosOriginalHtml;
      const select = document.getElementById("pincabos_language_select");
      if (select) {
        select.value = lang;
      }
    }
  }
  function translateString(original, lang) {
    if (lang === "fr") return original;
    const clean = normalizeText(original);
    if (lang === "en" && frToEn[clean]) {
      return original.replace(clean, frToEn[clean]);
    }
    return original;
  }
  function translateTextNodes(lang) {
    const walker = document.createTreeWalker(
      document.body,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: function (node) {
          if (!node.nodeValue || !normalizeText(node.nodeValue)) {
            return NodeFilter.FILTER_REJECT;
          }
          const parent = node.parentElement;
          if (!parent) return NodeFilter.FILTER_REJECT;
          const tag = parent.tagName.toLowerCase();
          if (["script", "style", "textarea", "pre", "code"].includes(tag)) {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      if (!node.__pincabosOriginalText) {
        node.__pincabosOriginalText = node.nodeValue;
      }
      node.nodeValue = translateString(node.__pincabosOriginalText, lang);
    });
  }
  function translateAttributes(lang) {
    document.querySelectorAll("input, button, option, a, select").forEach(el => {
      ["placeholder", "value", "title"].forEach(attr => {
        if (!el.hasAttribute || !el.hasAttribute(attr)) return;
        const key = "i18nOriginal" + attr;
        if (!el.dataset[key]) {
          el.dataset[key] = el.getAttribute(attr);
        }
        const original = el.dataset[key];
        el.setAttribute(attr, translateString(original, lang));
      });
    });
  }
  window.setPinCabOsLanguage = function (lang) {
    localStorage.setItem(STORAGE_KEY, lang);
    saveOriginalPageHtml();
    if (lang === "fr") {
      restoreOriginalPageHtml();
      return;
    }
    if (lang === "en") {
      restoreOriginalPageHtml();
      setTimeout(function () {
        translateTextNodes("en");
        translateAttributes("en");
      }, 100);
      return;
    }
  };
  window.addEventListener("load", function () {
    saveOriginalPageHtml();
    const saved = localStorage.getItem(STORAGE_KEY) || "fr";
    const select = document.getElementById("pincabos_language_select");
    if (select) {
      select.value = saved === "en" ? "en" : "fr";
    }
    setTimeout(function () {
      window.setPinCabOsLanguage(saved === "en" ? "en" : "fr");
    }, 300);
  });
})();
