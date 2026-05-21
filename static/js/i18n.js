// ── i18n — translation object and helpers ─────────────────────────
export const TRANSLATIONS = {
  en: {
    tagline:             "Open Knowledge, Everywhere",
    search_tab:          "🔍 Search",
    url_tab:             "🔗 URL",
    convert_tab:         "⚙️ Convert",
    history_tab:         "📋 History",
    collections_tab:     "🗂 Collections",
    search_label:        "Describe what you need",
    search_placeholder:  "e.g. research paper on transformers, or classic French novel…",
    sources_label:       "Sources",
    search_btn:          "Search",
    url_label:           "Open-access URL (PDF, document, …)",
    url_placeholder:     "https://arxiv.org/pdf/… or https://archive.org/…",
    url_label_short:     "URL",
    download_btn:        "Download",
    download_paper_title:"Download Paper",
    convert_file_label:  "File in downloads",
    select_file:         "— select file —",
    convert_to_label:    "Convert to",
    convert_btn:         "Convert",
    history_refresh_btn: "↺ Refresh history",
    new_collection_btn:  "+ New Collection",
    active_downloads:    "Active Downloads",
    clear_done:          "✕ Clear done",
    downloads_label:     "Downloads",
    refresh_btn:         "↺ refresh",
    results_label:       "Results",
    settings_btn:        "⚙ Settings",
    settings_title:      "⚙ Settings",
    settings_download_dir:   "Download Directory",
    settings_max_concurrent: "Max Concurrent Downloads",
    settings_language:   "Language",
    settings_auto_open:  "Auto-open viewer after download",
    settings_dark_mode:  "Dark mode",
    close_btn:           "Close",
    new_collection_title:"New Collection",
    coll_name_label:     "Name",
    coll_name_placeholder:"e.g. Linear Algebra Course",
    coll_desc_label:     "Description (optional)",
    cancel_btn:          "Cancel",
    create_btn:          "Create",
    add_to_coll_title:   "Add to Collection",
    add_to_coll_label:   "Choose collection",
    add_btn:             "Add",
    no_files:            "No files yet.",
    no_history:          "No history yet.",
    no_collections:      "No collections yet.",
    no_results:          "No results. Try different keywords or sources.",
    empty_state_msg:     "Search for open-access papers, books, or articles, or paste a direct URL — results appear here.",
    viewer_placeholder:  "Open a file to preview it here",
    viewer_no_file:      "No file open",
    file_missing:        "file missing",
    coll_delete_confirm: "Delete this collection and all its items?",
    coll_missing_name:   "Enter a name.",
    add_to_coll_missing: "Select a collection.",
    url_required:        "Paste an open-access URL first.",
    search_no_query:     "Enter a search query first.",
    convert_no_file:     "Select a file first.",
    gn_sources_label:    "Global North Sources",
    semantic_scholar_label: "Semantic Scholar",
    pubmed_label:        "PubMed",
    crossref_label:      "CrossRef",
    core_label:          "CORE",
    base_label:          "BASE",
    logout_btn:          "⏻ Sign out",
    login_title:         "Sign in to continue",
    login_email_label:   "Email",
    login_email_placeholder: "you@institution.edu",
    login_password_label:"Password",
    login_password_placeholder: "••••••••",
    login_btn:           "Sign in",
    login_error_invalid: "Invalid email or password.",
    login_error_network: "Network error — try again.",
    session_expired:     "Session expired. Please sign in again.",
    open_btn:            "Open",
    download_pdf_btn:    "⬇ Download PDF",
    ctx_open:            "Open in app",
    ctx_download:        "Download",
    ctx_copy:            "Copy link",
    // Admin
    admin_tab:                "📊 Admin",
    admin_analytics_title:    "Impact Analytics",
    coll_share_label:         "Share with institution",
    // 1.1 AI Demo
    ai_action_btn:      "AI",
    fab_analyse:        "Analyse",
    // 2.1 File list controls
    filter_files_placeholder: "Filter files…",
    sort_label:         "Sort",
    sort_name_az:       "Name (A–Z)",
    sort_name_za:       "Name (Z–A)",
    sort_newest:        "Newest first",
    sort_oldest:        "Oldest first",
    sort_largest:       "Largest first",
    sort_smallest:      "Smallest first",
    // 2.2 Truncation warning
    truncation_warning: "Only the first portion of this document was analysed.",
    // 2.4 Citation preview
    cite_modal_title:   "Export Citation",
    copy_btn:           "Copy",
    copied_feedback:    "Copied!",
    dl_bib:             "Download .bib",
    dl_ris:             "Download .ris",
    // 2.5 Save to collection
    save_to_collection: "+ Collection",
    // 3.3 Search history
    recent_searches:    "Recent searches",
    clear_recent:       "Clear",
    // 3.5 Convert in viewer
    convert_in_viewer:  "Convert",
    convert_tip:        "Tip: you can also convert files directly from the viewer toolbar.",
  },
  fr: {
    tagline:             "Le Savoir Ouvert, Partout",
    search_tab:          "🔍 Recherche",
    url_tab:             "🔗 URL",
    convert_tab:         "⚙️ Convertir",
    history_tab:         "📋 Historique",
    collections_tab:     "🗂 Collections",
    search_label:        "Décrivez ce dont vous avez besoin",
    search_placeholder:  "ex. article sur les transformeurs, ou roman classique français…",
    sources_label:       "Sources",
    search_btn:          "Rechercher",
    url_label:           "URL en libre accès (PDF, document, …)",
    url_placeholder:     "https://arxiv.org/pdf/… ou https://archive.org/…",
    url_label_short:     "URL",
    download_btn:        "Télécharger",
    download_paper_title:"Télécharger l'article",
    convert_file_label:  "Fichier dans les téléchargements",
    select_file:         "— sélectionner un fichier —",
    convert_to_label:    "Convertir en",
    convert_btn:         "Convertir",
    history_refresh_btn: "↺ Actualiser l'historique",
    new_collection_btn:  "+ Nouvelle collection",
    active_downloads:    "Téléchargements actifs",
    clear_done:          "✕ Effacer terminés",
    downloads_label:     "Téléchargements",
    refresh_btn:         "↺ actualiser",
    results_label:       "Résultats",
    settings_btn:        "⚙ Paramètres",
    settings_title:      "⚙ Paramètres",
    settings_download_dir:   "Répertoire de téléchargement",
    settings_max_concurrent: "Téléchargements simultanés max",
    settings_language:   "Langue",
    settings_auto_open:  "Ouvrir automatiquement après téléchargement",
    settings_dark_mode:  "Mode sombre",
    close_btn:           "Fermer",
    new_collection_title:"Nouvelle collection",
    coll_name_label:     "Nom",
    coll_name_placeholder:"ex. Cours d'algèbre linéaire",
    coll_desc_label:     "Description (optionnelle)",
    cancel_btn:          "Annuler",
    create_btn:          "Créer",
    add_to_coll_title:   "Ajouter à une collection",
    add_to_coll_label:   "Choisir une collection",
    add_btn:             "Ajouter",
    no_files:            "Aucun fichier pour l'instant.",
    no_history:          "Aucun historique pour l'instant.",
    no_collections:      "Aucune collection pour l'instant.",
    no_results:          "Aucun résultat. Essayez d'autres mots-clés ou sources.",
    empty_state_msg:     "Recherchez des articles, livres ou sujets, ou collez une URL directe — les résultats s'affichent ici.",
    viewer_placeholder:  "Ouvrez un fichier pour le prévisualiser ici",
    viewer_no_file:      "Aucun fichier ouvert",
    file_missing:        "fichier manquant",
    coll_delete_confirm: "Supprimer cette collection et tous ses éléments ?",
    coll_missing_name:   "Saisissez un nom.",
    add_to_coll_missing: "Sélectionnez une collection.",
    url_required:        "Collez d'abord une URL en libre accès.",
    search_no_query:     "Saisissez une requête de recherche.",
    convert_no_file:     "Sélectionnez d'abord un fichier.",
    gn_sources_label:    "Sources Global Nord",
    semantic_scholar_label: "Semantic Scholar",
    pubmed_label:        "PubMed",
    crossref_label:      "CrossRef",
    core_label:          "CORE",
    base_label:          "BASE",
    logout_btn:          "⏻ Déconnexion",
    login_title:         "Connectez-vous pour continuer",
    login_email_label:   "Adresse e-mail",
    login_email_placeholder: "vous@institution.edu",
    login_password_label:"Mot de passe",
    login_password_placeholder: "••••••••",
    login_btn:           "Se connecter",
    login_error_invalid: "E-mail ou mot de passe invalide.",
    login_error_network: "Erreur réseau — réessayez.",
    session_expired:     "Session expirée. Veuillez vous reconnecter.",
    open_btn:            "Ouvrir",
    download_pdf_btn:    "⬇ Télécharger PDF",
    ctx_open:            "Ouvrir dans l'appli",
    ctx_download:        "Télécharger",
    ctx_copy:            "Copier le lien",
    // Admin
    admin_tab:                "📊 Admin",
    admin_analytics_title:    "Analytique d'impact",
    coll_share_label:         "Partager avec l'institution",
    // 1.1 AI Demo
    ai_action_btn:      "IA",
    fab_analyse:        "Analyser",
    // 2.1 File list controls
    filter_files_placeholder: "Filtrer les fichiers…",
    sort_label:         "Trier",
    sort_name_az:       "Nom (A–Z)",
    sort_name_za:       "Nom (Z–A)",
    sort_newest:        "Plus récents",
    sort_oldest:        "Plus anciens",
    sort_largest:       "Plus grands",
    sort_smallest:      "Plus petits",
    // 2.2 Truncation warning
    truncation_warning: "Seule la première partie de ce document a été analysée.",
    // 2.4 Citation preview
    cite_modal_title:   "Exporter la citation",
    copy_btn:           "Copier",
    copied_feedback:    "Copié !",
    dl_bib:             "Télécharger .bib",
    dl_ris:             "Télécharger .ris",
    // 2.5 Save to collection
    save_to_collection: "+ Collection",
    // 3.3 Search history
    recent_searches:    "Recherches récentes",
    clear_recent:       "Effacer",
    // 3.5 Convert in viewer
    convert_in_viewer:  "Convertir",
    convert_tip:        "Astuce : vous pouvez aussi convertir depuis la barre d'outils du visualiseur.",
  }
};

export let currentLang = localStorage.getItem('lang') || 'fr';

export function t(key) {
  return (TRANSLATIONS[currentLang] || {})[key] || (TRANSLATIONS['en'] || {})[key] || key;
}

export function applyTranslations() {
  document.querySelectorAll('[data-i18n]').forEach(el => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  const btnLang = document.getElementById('btnLang');
  if (btnLang) btnLang.textContent = currentLang === 'fr' ? 'EN' : 'FR';
  const enBtn = document.getElementById('settingLangEn');
  const frBtn = document.getElementById('settingLangFr');
  if (enBtn && frBtn) {
    const active = 'border-color:var(--teal);color:var(--teal)';
    enBtn.style.cssText = currentLang === 'en' ? active : '';
    frBtn.style.cssText = currentLang === 'fr' ? active : '';
  }
}

export function setLang(lang) {
  currentLang = lang;
  localStorage.setItem('lang', lang);
  applyTranslations();
}
