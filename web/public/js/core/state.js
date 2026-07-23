/**
 * Etat applicatif central (mutable, observable via bus).
 */
import { bus } from './bus.js';
import { defaultSettings } from '../models/settings.js';

export const state = {
    view: 'feed',           // feed | favoris | sources | jobs | tendances | radar | settings
    feedMode: 'all',        // all | favorites
    sites: [],
    articles: [],
    selectedArticleId: null,
    viewingSiteId: null,
    jobs: [],
    selectedJobId: null,
    jobsFilter: 'all',
    trends: [],
    trendsDays: 30,
    trendsKind: 'all',
    selectedTrendTerm: null,
    radarIdeas: [],
    radarDays: 30,
    radarTheme: 'all',
    selectedRadarTheme: null,
    settings: { ...defaultSettings() },
    currentAnalysisId: null,
    pendingVictorySiteId: null,
};

export function patchState(partial, event = 'state:changed') {
    Object.assign(state, partial);
    bus.emit(event, state);
    bus.emit('state:changed', state);
}

export function setView(view) {
    patchState({
        view,
        feedMode: view === 'favoris' ? 'favorites' : (view === 'feed' ? 'all' : state.feedMode),
    }, 'view:changed');
}
