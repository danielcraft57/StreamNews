/**
 * Bootstrap StreamNews — Material Web + architecture en couches.
 */
import '../vendor/material.js';
import { bus } from './core/bus.js';
import { state, setView, patchState } from './core/state.js';
import { api } from './services/api.js';
import { storage } from './services/storage.js';
import { connectRealtime } from './services/realtime.js';
import { showToast } from './ui/toast.js';
import * as articleModel from './models/article.js';
import * as siteModel from './models/site.js';
import { createJob, jobStatusLabel, jobTypeIcon, jobTypeLabel } from './models/job.js';
import { defaultSettings } from './models/settings.js';
import {
    bindAddSourceDialog,
    bindSettingsForm,
    hydrateSettingsForm,
} from './ui/material-bindings.js';
import * as feedView from './views/feed-view.js';
import * as readerView from './views/reader-view.js';
import * as sourcesView from './views/sources-view.js';
import * as jobsView from './views/jobs-view.js';
import * as searchView from './views/search-view.js';
import * as feedChips from './views/feed-chips.js';
import * as searchService from './services/search.js';
import * as trendsView from './views/trends-view.js';
import * as radarView from './views/radar-view.js';
import * as chips from './ui/chips.js';

window.SN = {
    bus,
    state,
    setView,
    patchState,
    api,
    storage,
    connectRealtime,
    showToast,
    articleModel,
    siteModel,
    createJob,
    jobStatusLabel,
    jobTypeIcon,
    jobTypeLabel,
    defaultSettings,
    bindAddSourceDialog,
    bindSettingsForm,
    hydrateSettingsForm,
    feedView,
    readerView,
    sourcesView,
    jobsView,
    searchView,
    feedChips,
    searchService,
    trendsView,
    radarView,
    chips,
};

bus.on('toast', (payload) => {
    const message = typeof payload === 'string' ? payload : payload?.message;
    const type = payload?.type || 'info';
    if (message) showToast(message, type);
});

// Orchestrateur legacy (migration progressive depuis monolithe)
await import('../app.js');
