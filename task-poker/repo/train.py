import gc, json, math, os, sys, time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.dataset as ds
import pyarrow.parquet as pq
from scipy.stats import rankdata

# ML models
from sklearn.ensemble import ExtraTreesClassifier
from sklearn.impute import SimpleImputer
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import Pipeline
import lightgbm as lgb
import xgboost as xgb
from catboost import CatBoostClassifier

SEED = 20260918
N_FOLDS = 5
POOL_LIMIT = None
WORKERS = max(1, (os.cpu_count() or 2) - 1)

CANDIDATES = [
    Path('/kaggle/input/detect-suspicious-value-transfers-in-poker'),
    Path('/kaggle/input/competitions/detect-suspicious-value-transfers-in-poker'),
    Path('data'),
    Path('../data')
]
DATA_DIR = next((p for p in CANDIDATES if (p / 'hands.parquet').exists()), None)
if DATA_DIR is None:
    raise SystemExit('Could not find the competition files; set DATA_DIR manually.')
OUT_DIR = Path('/kaggle/working') if Path('/kaggle/working').exists() else Path('.')
print('data:', DATA_DIR, '| workers:', WORKERS)


# === INPUT INGESTION ===
labels = pd.read_csv(DATA_DIR / 'development_labels.csv')
evidence = pd.read_csv(DATA_DIR / 'development_evidence.csv')
eval_pairs = pd.read_csv(DATA_DIR / 'evaluation_pairs.csv')
template = pd.read_csv(DATA_DIR / 'sample_submission.csv')
hands = pq.read_table(DATA_DIR / 'hands.parquet',
                      columns=['hand_id', 'table_id', 'phase', 'big_blind', 'board_cards']).to_pandas()

print('labels', labels.shape, '| positives', int(labels.label.sum()), '| evidence rows', len(evidence))
print('evaluation pairs', len(eval_pairs), '| template', len(template))
print(labels.behavior_family.value_counts().to_dict())
print(hands.phase.value_counts().to_dict(), '| pools', hands.table_id.nunique())

pools = sorted(hands.table_id.unique())
if POOL_LIMIT:
    pools = pools[:POOL_LIMIT]
    keep = set(pools)
    hands = hands[hands.table_id.isin(keep)]
    print('SMOKE RUN on', len(pools), 'pools')

pair_key = lambda a, b: (a, b) if a < b else (b, a)
dev_pairs = labels[['pair_id', 'player_1', 'player_2', 'label', 'behavior_family']].copy()
truth_evidence = evidence.sort_values(['pair_id', 'evidence_rank']).groupby('pair_id').hand_id.apply(list).to_dict()


# === VECTORIZED CARD EVALUATOR ===
RANKS, SUITS = '23456789TJQKA', 'cdhs'
CARD = {r + s: RANKS.index(r) * 4 + SUITS.index(s) for r in RANKS for s in SUITS}

def straight_lookup():
    table = np.full(1 << 13, -1, np.int8)
    for mask in range(1 << 13):
        if mask & 0b1000000001111 == 0b1000000001111:
            table[mask] = 3                      # wheel: A-2-3-4-5
        for top in range(4, 13):
            window = sum(1 << r for r in range(top - 4, top + 1))
            if mask & window == window:
                table[mask] = top
    return table

STRAIGHT = straight_lookup()

def hand_values(cards):
    """cards: (n, 5..7) int array of card codes -> (n,) comparable strength values."""
    cards = np.asarray(cards)
    n = len(cards)
    ranks, suits = cards >> 2, cards & 3
    counts = np.zeros((n, 13), np.int8)
    np.add.at(counts, (np.repeat(np.arange(n), cards.shape[1]), ranks.ravel()), 1)
    suit_counts = np.zeros((n, 4), np.int8)
    np.add.at(suit_counts, (np.repeat(np.arange(n), cards.shape[1]), suits.ravel()), 1)
    present = (counts > 0).astype(np.int64)
    mask = present @ (1 << np.arange(13))
    straight = STRAIGHT[mask]
    flush_suit = suit_counts.argmax(1)
    has_flush = suit_counts.max(1) >= 5
    in_flush = (suits == flush_suit[:, None]) & has_flush[:, None]
    fmask = np.zeros((n, 13), np.int64)
    fmask[np.repeat(np.arange(n), cards.shape[1])[in_flush.ravel()], ranks.ravel()[in_flush.ravel()]] = 1
    flush_bits = fmask @ (1 << np.arange(13))
    straight_flush = np.where(has_flush, STRAIGHT[flush_bits], -1)

    def nth(matrix, k):
        """rank index of the k-th highest True column, or -1"""
        desc = matrix[:, ::-1]
        hit = desc & (np.cumsum(desc, 1) == k)
        return np.where(hit.any(1), 12 - hit.argmax(1), -1)

    quad, trip1 = nth(counts == 4, 1), nth(counts == 3, 1)
    trip2, pair1, pair2 = nth(counts == 3, 2), nth(counts == 2, 1), nth(counts == 2, 2)
    singles, anyc = counts == 1, counts > 0
    value = np.zeros(n, np.int64)
    done = np.zeros(n, bool)

    def encode(cat, *slots):
        out = np.full(n, cat, np.int64)
        for i in range(5):
            out = out * 15 + (np.maximum(slots[i], -1) + 1 if i < len(slots) else 0)
        return out

    def assign(cond, encoded):
        nonlocal value, done
        use = cond & ~done
        value = np.where(use, encoded, value)
        done |= use

    assign(straight_flush >= 0, encode(8, straight_flush))
    assign(quad >= 0, encode(7, quad, nth(anyc & (counts != 4), 1)))
    full_pair = np.maximum(trip2, pair1)
    assign((trip1 >= 0) & (full_pair >= 0), encode(6, trip1, full_pair))
    assign(has_flush, encode(5, *[nth(fmask.astype(bool), k) for k in range(1, 6)]))
    assign(straight >= 0, encode(4, straight))
    assign(trip1 >= 0, encode(3, trip1, nth(singles, 1), nth(singles, 2)))
    not_pair = anyc & (np.arange(13) != pair1[:, None]) & (np.arange(13) != pair2[:, None])
    assign(pair2 >= 0, encode(2, pair1, pair2, nth(not_pair, 1)))
    assign(pair1 >= 0, encode(1, pair1, nth(singles, 1), nth(singles, 2), nth(singles, 3)))
    assign(~done, encode(0, *[nth(anyc, k) for k in range(1, 6)]))
    return value


# === REPLAY & FEATURE EXTRACTION ===
AGGRESSIVE = {'bet', 'raise'}
PRE, POST = 0, 1

def chen(c1, c2):
    r1, r2 = c1 >> 2, c2 >> 2
    hi, lo = max(r1, r2), min(r1, r2)
    base = {12: 10.0, 11: 8.0, 10: 7.0, 9: 6.0}.get(hi, (hi + 2) / 2.0)
    score = base * (2 if r1 == r2 else 1)
    if r1 == r2:
        score = max(score, 5.0)
    if (c1 & 3) == (c2 & 3):
        score += 2
    gap = hi - lo - 1
    score -= {0: 0, 1: 1, 2: 2, 3: 4}.get(gap, 5)
    if gap <= 1 and hi < 10 and r1 != r2:
        score += 1
    return score

def classify(action, amount, to_call):
    if action == 'fold':
        return 0
    if action in AGGRESSIVE or (action == 'all_in' and amount > to_call):
        return 2
    return 1

FEATURES = ['both_vpip', 'both_weak_entry', 'both_showdown', 'pot_bb', 'net_gap_bb', 'opposing_proxy_bb',
            'fold_vs_partner', 'call_vs_partner', 'raise_vs_partner', 'n_partner_priced',
            'fold_vs_field', 'call_vs_field', 'raise_vs_field', 'n_field_priced',
            'hu_postflop_checks', 'hu_postflop_bets', 'partner_aggr_while_live',
            'loser_had_better_hand', 'winner_not_best', 'strength_gap', 'weak_entry_after_partner']

def pool_pair_hands(task):
    pool, phase, wanted = task
    hand_tbl = ds.dataset(DATA_DIR / 'hands.parquet').to_table(
        filter=(ds.field('table_id') == pool) & (ds.field('phase') == phase),
        columns=['hand_id', 'big_blind', 'board_cards']).to_pandas()
    if not len(hand_tbl):
        return pd.DataFrame(columns=['pair_id', 'hand_id', *FEATURES])
    ids = hand_tbl.hand_id.tolist()
    seats = ds.dataset(DATA_DIR / 'seats.parquet').to_table(
        filter=ds.field('hand_id').isin(ids),
        columns=['hand_id', 'player_id', 'seat_no', 'hole_card_1', 'hole_card_2',
                 'total_contribution', 'net_chips', 'folded', 'went_to_showdown']).to_pandas()
    actions = ds.dataset(DATA_DIR / 'actions.parquet').to_table(
        filter=ds.field('hand_id').isin(ids),
        columns=['hand_id', 'action_no', 'street', 'player_id', 'action', 'amount', 'to_call']).to_pandas()
    seats = seats.sort_values(['hand_id', 'seat_no'])
    actions = actions.sort_values(['hand_id', 'action_no'])
    seat_groups = {h: g for h, g in seats.groupby('hand_id', sort=False)}
    act_groups = {h: g for h, g in actions.groupby('hand_id', sort=False)}

    rows = []
    for hand in hand_tbl.itertuples(index=False):
        s = seat_groups.get(hand.hand_id)
        a = act_groups.get(hand.hand_id)
        if s is None or a is None:
            continue
        players = s.player_id.to_numpy()
        pairs = [(i, j, wanted[key]) for i in range(len(players)) for j in range(i + 1, len(players))
                 if (key := (players[i], players[j]) if players[i] < players[j] else (players[j], players[i])) in wanted]
        if not pairs:
            continue
        bb = float(hand.big_blind)
        holes = np.array([[CARD[c1], CARD[c2]] for c1, c2 in zip(s.hole_card_1, s.hole_card_2)])
        chens = np.array([chen(h[0], h[1]) for h in holes])
        contrib = s.total_contribution.to_numpy() / bb
        net = s.net_chips.to_numpy() / bb
        showdown = s.went_to_showdown.to_numpy()
        n = len(players)
        index = {p: k for k, p in enumerate(players)}

        board = [CARD[c] for c in (hand.board_cards or '').split()]
        strength = np.full(n, np.nan)
        if len(board) == 5:
            strength = hand_values(np.concatenate([holes, np.tile(board, (n, 1))], axis=1)).astype(float)

        resp = np.zeros((n, n, 3))
        field = np.zeros((n, 3))
        vpip = np.zeros(n, bool)
        entered_order = []
        aggr_while = np.zeros((n, n))
        hu_checks = np.zeros((n, n))
        hu_bets = np.zeros((n, n))
        live = set(range(n))
        street, setter = None, -1
        for act in a.itertuples(index=False):
            k = index.get(act.player_id)
            if k is None:
                continue
            if act.street != street:
                street, setter = act.street, -1
            post = act.street != 'preflop'
            cls = classify(act.action, act.amount, act.to_call)
            priced = act.to_call > 0
            if priced:
                field[k, cls] += 1
                if setter >= 0:
                    resp[k, setter, cls] += 1
            if not post and cls > 0 and act.amount > 0 and not vpip[k]:
                vpip[k] = True
                entered_order.append(k)
            if cls == 2:
                for other in live:
                    if other != k:
                        aggr_while[k, other] += 1
            if post and not priced and len(live) == 2:
                other = next(iter(live - {k}), None)
                if other is not None:
                    (hu_checks if cls == 1 else hu_bets)[k, other] += 1
            if cls == 0:
                live.discard(k)
            elif cls == 2:
                setter = k

        for i, j, pid in pairs:
            both_in = bool(vpip[i] and vpip[j])
            weak_both = bool(both_in and chens[i] < 8 and chens[j] < 8)
            second_weak = 0.0
            if both_in and len(entered_order) >= 2:
                order = [k for k in entered_order if k in (i, j)]
                if len(order) == 2 and chens[order[1]] < 8:
                    second_weak = 1.0
            partner = resp[i, j] + resp[j, i]
            outsiders = (field[i] + field[j]) - partner
            loser, winner = (i, j) if net[i] < net[j] else (j, i)
            strength_gap = float(strength[i] - strength[j]) if np.isfinite(strength[i]) and np.isfinite(strength[j]) else np.nan
            loser_better = float(strength[loser] > strength[winner]) if np.isfinite(strength_gap) else np.nan
            winner_not_best = float(np.isfinite(strength).any() and strength[winner] < np.nanmax(strength)) if np.isfinite(strength_gap) else np.nan
            rows.append((pid, hand.hand_id, float(both_in), float(weak_both),
                         float(showdown[i] and showdown[j]), float(contrib.sum()), float(abs(net[i] - net[j])),
                         float(min(max(-net[i], 0), max(net[j], 0)) + min(max(-net[j], 0), max(net[i], 0))),
                         partner[0], partner[1], partner[2], float(partner.sum()),
                         outsiders[0], outsiders[1], outsiders[2], float(outsiders.sum()),
                         float(hu_checks[i, j] + hu_checks[j, i]), float(hu_bets[i, j] + hu_bets[j, i]),
                         float(aggr_while[i, j] + aggr_while[j, i]),
                         loser_better, winner_not_best, strength_gap, second_weak))
    return pd.DataFrame(rows, columns=['pair_id', 'hand_id', *FEATURES])


# === PAIR AGGREGATION WITH ENHANCED INVARIANTS ===
RATE_COLS = ['both_vpip', 'both_weak_entry', 'both_showdown', 'loser_had_better_hand', 'winner_not_best',
             'weak_entry_after_partner']
MEAN_COLS = ['pot_bb', 'net_gap_bb', 'opposing_proxy_bb', 'strength_gap']

def aggregate_pairs(frame):
    if not len(frame):
        return pd.DataFrame()
    g = frame.groupby('pair_id', sort=False)
    out = g[RATE_COLS + MEAN_COLS].mean()
    out['shared_hands'] = g.size()
    out['max_opposing_proxy'] = g.opposing_proxy_bb.max()
    out['p90_opposing_proxy'] = g.opposing_proxy_bb.quantile(.9)
    sums = g[['fold_vs_partner', 'call_vs_partner', 'raise_vs_partner', 'n_partner_priced',
              'fold_vs_field', 'call_vs_field', 'raise_vs_field', 'n_field_priced',
              'hu_postflop_checks', 'hu_postflop_bets', 'partner_aggr_while_live']].sum()
    for kind in ('fold', 'call', 'raise'):
        p = sums[f'{kind}_vs_partner'] / sums.n_partner_priced.clip(lower=1)
        f = sums[f'{kind}_vs_field'] / sums.n_field_priced.clip(lower=1)
        out[f'{kind}_rate_partner'] = p
        out[f'{kind}_rate_field'] = f
        out[f'{kind}_contrast'] = p - f
    out['partner_priced_n'] = sums.n_partner_priced
    out['hu_check_rate'] = sums.hu_postflop_checks / (sums.hu_postflop_checks + sums.hu_postflop_bets).clip(lower=1)
    out['aggr_while_live_per_hand'] = sums.partner_aggr_while_live / out.shared_hands
    
    # Enhanced scale-invariant features
    out['transfer_asymmetry'] = out['max_opposing_proxy'] / (out['pot_bb'].clip(lower=1.0) * out['shared_hands'].clip(lower=1.0))
    out['soft_play_rate'] = out['hu_check_rate'] * (1.0 - out['raise_rate_partner'].clip(0, 1))

    return out.reset_index()


# === DEVELOPMENT PHASE EXTRACTION ===
t0 = time.time()
wanted_dev = {pair_key(r.player_1, r.player_2): r.pair_id for r in dev_pairs.itertuples(index=False)}
dev_tasks = [(p, 'development', wanted_dev) for p in pools]
frames = []
with ProcessPoolExecutor(max_workers=WORKERS) as ex:
    for i, part in enumerate(ex.map(pool_pair_hands, dev_tasks), 1):
        if len(part):
            frames.append(part)
        if i % 50 == 0:
            print(f'development {i}/{len(dev_tasks)} pools, {time.time()-t0:.0f}s', flush=True)
dev_hand_rows = pd.concat(frames, ignore_index=True)
del frames; gc.collect()
print('development pair-hand rows:', len(dev_hand_rows), f'{time.time()-t0:.0f}s')

dev_features = aggregate_pairs(dev_hand_rows).merge(dev_pairs, on='pair_id', how='inner')
seat_pool = pq.read_table(DATA_DIR / 'seats.parquet', columns=['hand_id', 'player_id']).to_pandas()
seat_pool = seat_pool.merge(hands[['hand_id', 'table_id']], on='hand_id').drop_duplicates(['player_id'])
player_pool = dict(zip(seat_pool.player_id, seat_pool.table_id))
dev_features['table_id'] = dev_features.player_1.map(player_pool)
PAIR_FEATURES = [c for c in dev_features.columns
                 if c not in {'pair_id', 'player_1', 'player_2', 'label', 'behavior_family', 'table_id'}]
print('pair features:', len(PAIR_FEATURES), '| labelled pairs with rows:', len(dev_features))


# === QUAD-ENSEMBLE TRAINING WITH GROUPKFOLD ===
X = dev_features[PAIR_FEATURES].to_numpy(dtype=float)
y = dev_features.label.to_numpy(int)
groups = dev_features.table_id.to_numpy()
folds = list(GroupKFold(n_splits=N_FOLDS).split(X, y, groups))
dev_features['fold'] = -1

# Individual pipelines
def get_et(seed):
    return Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)),
                     ('model', ExtraTreesClassifier(n_estimators=300, min_samples_leaf=4, max_features=0.8,
                                                    class_weight='balanced', random_state=seed, n_jobs=-1))])

def get_cb(seed):
    return Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)),
                     ('model', CatBoostClassifier(iterations=400, depth=6, learning_rate=0.03, l2_leaf_reg=5.0,
                                                   auto_class_weights='Balanced', random_seed=seed,
                                                   allow_writing_files=False, verbose=False, thread_count=-1))])

def get_lgb(seed):
    return Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)),
                     ('model', lgb.LGBMClassifier(n_estimators=400, max_depth=5, num_leaves=28, learning_rate=0.03,
                                                  class_weight='balanced', subsample=0.8, colsample_bytree=0.7,
                                                  path_smooth=5.0, random_state=seed, verbose=-1, n_jobs=-1))])

def get_xgb(seed):
    return Pipeline([('impute', SimpleImputer(strategy='median', add_indicator=True, keep_empty_features=True)),
                     ('model', xgb.XGBClassifier(n_estimators=400, max_depth=5, learning_rate=0.03,
                                                 scale_pos_weight=4.0, min_child_weight=8, subsample=0.8,
                                                 colsample_bytree=0.7, random_state=seed, tree_method='hist', n_jobs=-1))])

oof_et = np.zeros(len(dev_features))
oof_cb = np.zeros(len(dev_features))
oof_lgb = np.zeros(len(dev_features))
oof_xgb = np.zeros(len(dev_features))

print('[Training Quad-Ensemble Models across 5 folds]...')
for k, (tr, va) in enumerate(folds):
    dev_features.loc[dev_features.index[va], 'fold'] = k
    m_et = get_et(SEED + k).fit(X[tr], y[tr])
    m_cb = get_cb(SEED + k).fit(X[tr], y[tr])
    m_lgb = get_lgb(SEED + k).fit(X[tr], y[tr])
    m_xgb = get_xgb(SEED + k).fit(X[tr], y[tr])

    oof_et[va] = m_et.predict_proba(X[va])[:, 1]
    oof_cb[va] = m_cb.predict_proba(X[va])[:, 1]
    oof_lgb[va] = m_lgb.predict_proba(X[va])[:, 1]
    oof_xgb[va] = m_xgb.predict_proba(X[va])[:, 1]

# Fit full models on all dev data
final_et = get_et(SEED).fit(X, y)
final_cb = get_cb(SEED).fit(X, y)
final_lgb = get_lgb(SEED).fit(X, y)
final_xgb = get_xgb(SEED).fit(X, y)

from sklearn.metrics import average_precision_score
w_cb = float(os.environ.get('W_CB', os.environ.get('w_cb', '0.35')))
w_lgb = float(os.environ.get('W_LGB', os.environ.get('w_lgb', '0.30')))
w_et = float(os.environ.get('W_ET', os.environ.get('w_et', '0.20')))
w_xgb = float(os.environ.get('W_XGB', os.environ.get('w_xgb', '0.15')))
_wsum = max(w_cb + w_lgb + w_et + w_xgb, 1e-9)
w_cb, w_lgb, w_et, w_xgb = w_cb / _wsum, w_lgb / _wsum, w_et / _wsum, w_xgb / _wsum
oof_ens = w_cb * oof_cb + w_lgb * oof_lgb + w_et * oof_et + w_xgb * oof_xgb
print('blend weights cb/lgb/et/xgb:', round(w_cb, 4), round(w_lgb, 4), round(w_et, 4), round(w_xgb, 4))
print('OOF pair AP ExtraTrees:', round(average_precision_score(y, oof_et), 6))
print('OOF pair AP CatBoost:  ', round(average_precision_score(y, oof_cb), 6))
print('OOF pair AP LightGBM:  ', round(average_precision_score(y, oof_lgb), 6))
print('OOF pair AP XGBoost:   ', round(average_precision_score(y, oof_xgb), 6))
print('OOF pair AP Quad-Blend:', round(average_precision_score(y, oof_ens), 6))
OOF_PAIR_AP = float(average_precision_score(y, oof_ens))


# === FAMILY BEHAVIOR CLASSIFIER ===
positives = dev_features[dev_features.label.eq(1)].reset_index(drop=True)
Xp, yp = positives[PAIR_FEATURES].to_numpy(dtype=float), positives.behavior_family.to_numpy()
fam_oof = np.empty(len(positives), dtype=object)
for tr, va in GroupKFold(n_splits=N_FOLDS).split(Xp, yp, positives.table_id):
    fam = get_et(SEED + 7).fit(Xp[tr], yp[tr])
    fam_oof[va] = fam.predict(Xp[va])
print('OOF family accuracy on confirmed targets:', round((fam_oof == yp).mean(), 4))
family_model = get_et(SEED + 7).fit(Xp, yp)


# === EVIDENCE HAND RANKER ===
HAND_FEATURES = [c for c in FEATURES]
listed = evidence.assign(listed=1)[['pair_id', 'hand_id', 'listed']]
pos_ids = set(positives.pair_id)
train_hands = dev_hand_rows[dev_hand_rows.pair_id.isin(pos_ids)].merge(listed, on=['pair_id', 'hand_id'], how='left')
train_hands['listed'] = train_hands.listed.fillna(0)
train_hands = train_hands.merge(dev_features[['pair_id', 'behavior_family', 'table_id', 'fold']], on='pair_id')
print('training hands:', len(train_hands), '| listed:', int(train_hands.listed.sum()))

def fit_ranker(frame, seed):
    frame = frame.sort_values('pair_id')
    groups = frame.groupby('pair_id', sort=False).size().to_numpy()
    d = xgb.DMatrix(frame[HAND_FEATURES].to_numpy(dtype=float), label=frame.listed.to_numpy(), group=groups,
                    missing=np.nan)
    params = dict(objective='rank:map', eta=0.1, max_depth=5, subsample=0.9, colsample_bytree=0.8,
                  min_child_weight=5, seed=seed, nthread=WORKERS, eval_metric='map@5')
    return xgb.train(params, d, num_boost_round=180)

def score_hands(model, frame):
    if not len(frame):
        return np.zeros(0)
    return model.predict(xgb.DMatrix(frame[HAND_FEATURES].to_numpy(dtype=float), missing=np.nan))

FAMILIES = sorted(positives.behavior_family.unique())
MIN_LISTED = 40

def family_rankers_for(frame, seed):
    out = {}
    for f in FAMILIES:
        block = frame[frame.behavior_family.eq(f)]
        if block.listed.sum() >= MIN_LISTED:
            out[f] = fit_ranker(block, seed)
    return out

generic_model = fit_ranker(train_hands, SEED + 11)
family_rankers = family_rankers_for(train_hands, SEED + 21)
print('family rankers trained:', sorted(family_rankers) or '(none: generic fallback everywhere)')


# === EVALUATION PHASE INFERENCE ===
wanted_eval = {}
for r in eval_pairs.itertuples(index=False):
    wanted_eval[pair_key(r.player_1, r.player_2)] = r.pair_id
eval_tasks = [(p, 'evaluation', wanted_eval) for p in pools]

risk_rows, evidence_rows = [], []
t0 = time.time()
with ProcessPoolExecutor(max_workers=WORKERS) as ex:
    for i, part in enumerate(ex.map(pool_pair_hands, eval_tasks), 1):
        if not len(part):
            continue
        feats = aggregate_pairs(part)
        matrix = feats.reindex(columns=PAIR_FEATURES).to_numpy(dtype=float)

        # Global probability prediction via Quad-Ensemble
        p_et = final_et.predict_proba(matrix)[:, 1]
        p_cb = final_cb.predict_proba(matrix)[:, 1]
        p_lgb = final_lgb.predict_proba(matrix)[:, 1]
        p_xgb = final_xgb.predict_proba(matrix)[:, 1]
        feats['risk_score'] = 0.35 * p_cb + 0.30 * p_lgb + 0.20 * p_et + 0.15 * p_xgb

        feats['predicted_behavior'] = family_model.predict(matrix)
        risk_rows.append(feats[['pair_id', 'risk_score', 'predicted_behavior', 'max_opposing_proxy']])

        # Score hands with per-family ranker + GTO saliency bonus
        block = part.merge(feats[['pair_id', 'predicted_behavior']], on='pair_id')
        scores = score_hands(generic_model, block)
        for f, model in family_rankers.items():
            m = (block.predicted_behavior == f).to_numpy()
            if m.any():
                scores[m] = score_hands(model, block[m])
        
        # GTO blunder bonus
        opp_proxy = block['opposing_proxy_bb'].to_numpy(dtype=float)
        loser_better = np.nan_to_num(block['loser_had_better_hand'].to_numpy(dtype=float))
        winner_not_best = np.nan_to_num(block['winner_not_best'].to_numpy(dtype=float))
        saliency = 2.0 * opp_proxy + 4.0 * loser_better + 6.0 * winner_not_best
        block['score'] = scores + 0.15 * saliency

        best = (block.sort_values(['pair_id', 'score'], ascending=[True, False])
                     .groupby('pair_id').head(5)[['pair_id', 'hand_id']])
        evidence_rows.append(best)
        if i % 50 == 0:
            print(f'evaluation {i}/{len(eval_tasks)} pools, {time.time()-t0:.0f}s', flush=True)

pair_scores = pd.concat(risk_rows, ignore_index=True)
evidence_top = pd.concat(evidence_rows, ignore_index=True)
print('scored pairs:', len(pair_scores), '| evidence rows:', len(evidence_top))


# === PIVOT EVIDENCE AND FORMAT SUBMISSION ===
wide = (evidence_top.assign(rank=evidence_top.groupby('pair_id').cumcount() + 1)
        .pivot(index='pair_id', columns='rank', values='hand_id')
        .reindex(columns=[1, 2, 3, 4, 5]))
wide.columns = [f'evidence_hand_{c}' for c in wide.columns]

submission = template[['pair_id']].merge(pair_scores, on='pair_id', how='left').merge(wide, on='pair_id', how='left')

# Global Zero-Tie Micro-Ranking
sec = submission['max_opposing_proxy'].fillna(0.0).to_numpy(dtype=float)
sec_rank = (rankdata(sec, method='ordinal') - 1.0) / len(submission)
submission['risk_score'] = np.clip(
    submission['risk_score'].fillna(0.0).to_numpy(dtype=float) + 1e-9 * sec_rank, 0.0, 1.0
)
submission.drop(columns=['max_opposing_proxy'], inplace=True)

submission['predicted_behavior'] = submission.predicted_behavior.fillna('none')
for c in [f'evidence_hand_{i}' for i in range(1, 6)]:
    submission[c] = submission[c].fillna('NO_EVIDENCE')
submission = submission[template.columns.tolist()]

# Verification assertions
assert len(submission) == len(template), 'row count mismatch'
assert submission.pair_id.tolist() == template.pair_id.tolist(), 'row order mismatch'
assert submission.risk_score.between(0, 1).all() and np.isfinite(submission.risk_score).all()
assert submission.predicted_behavior.isin(
    {'none', 'directed_transfer', 'soft_play', 'coordinated_isolation', 'other_coordination'}).all()
ev_cols = [f'evidence_hand_{i}' for i in range(1, 6)]
dupes = submission[ev_cols].apply(lambda r: len({x for x in r if x != 'NO_EVIDENCE'}) !=
                                  len([x for x in r if x != 'NO_EVIDENCE']), axis=1)
assert not dupes.any(), 'repeated evidence within a pair is invalid'

path = OUT_DIR / 'submission.csv'
submission.to_csv(path, index=False)
print('wrote', path, submission.shape)
print('Unique risk scores:', submission['risk_score'].nunique(), '(Zero-Tie Verified)')
print('Behavior distribution:', submission['predicted_behavior'].value_counts().to_dict())
print('Completed successfully in', f'{time.time()-t0:.1f}s')

# AutoScientists metric bridge: minimize val_loss == maximize OOF pair AP
_metrics = {
    'val_loss': float(1.0 - OOF_PAIR_AP),
    'oof_pair_ap': float(OOF_PAIR_AP),
    'exp_id': os.environ.get('EXP_ID', 'poker_quad'),
    'blend': {'w_cb': w_cb, 'w_lgb': w_lgb, 'w_et': w_et, 'w_xgb': w_xgb},
}
print(json.dumps(_metrics), flush=True)
(OUT_DIR / 'metrics.json').write_text(json.dumps(_metrics), encoding='utf-8')
