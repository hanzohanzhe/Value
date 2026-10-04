"""Auditable period cash transfers, distinct from physical operating costs.

Only source-configured downward prices are repaired into signed agent cash.
Nuclear source fees remain unresolved legacy diagnostics, not new revenue.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

from .doctoral_market import COST_PROFILE, SETTLEMENT_RULE


def settlement_report(outcome) -> dict:
    raw = outcome.to_dict()
    assets = tuple(raw['generation_mwh_by_asset'])
    connections = set(assets) - set(outcome.next_state.generator_memory) - set(outcome.next_state.storage_capacities_mwh)
    transactions, rows = [], []
    asset_market_cash = {name: 0.0 for name in assets}

    def transfer(stage, name, mwh, signed_receipt, payer, receiver, market=False):
        # Quantity is a positive accepted volume, price/cash preserve sign.
        # Negative cash reverses payer/payee; zero records are deliberately kept.
        price = signed_receipt / mwh if mwh else 0.0
        if not mwh and abs(signed_receipt) > 1e-7:
            raise ValueError('Nonzero settlement cash without accepted volume')
        if signed_receipt < 0:
            payer, receiver = receiver, payer
        amount = abs(signed_receipt)
        transactions.append(dict(transaction_id=f"{raw['input_sha256']}:{outcome.next_state.next_absolute_period-1}:{stage}:{name}",
            stage=stage, asset_id=name, payer=payer, payee=receiver,
            quantity_mwh=mwh, price_gbp_per_mwh=price, signed_receipt_gbp=signed_receipt,
            amount_gbp=amount, payer_cash_gbp=-amount, payee_cash_gbp=amount,
            rule_version=SETTLEMENT_RULE))
        if market:
            asset_market_cash[name] += signed_receipt

    maps = [key for key in raw if key.endswith('_by_asset')]
    for name in assets:
        for stage, qty, cash, payer in (
            ('ahead', 'ahead_scheduled_mwh_by_asset', 'ahead_income_gbp_by_asset', 'aggregate_buyer'),
            ('upward', 'upward_accepted_mwh_by_asset', 'upward_income_gbp_by_asset', 'system_settlement'),
            ('downward', 'downward_accepted_mwh_by_asset', 'downward_cash_gbp_by_asset', 'system_settlement')):
            transfer(stage, name, raw[qty][name], raw[cash][name], payer, 'asset:'+name, True)
        if name in connections:
            # Connection clearing account receives the source upward settlement
            # and pays the observed external procurement price exactly once.
            transfer('external_import_procurement', name, raw['generation_mwh_by_asset'][name],
                raw['operating_cost_gbp_by_asset'][name], 'asset:'+name, 'external:'+name)
            transfer('external_export', name, raw['export_mwh_by_asset'][name],
                raw['export_receipt_gbp_by_asset'][name], 'external:'+name, 'system_settlement')
        rows.append({'asset_id': name, **{key.removesuffix('_by_asset'): raw[key][name] for key in maps}})
    cash_residual = math.fsum(t['payer_cash_gbp'] + t['payee_cash_gbp'] for t in transactions)
    expected_cash = {name: raw['ahead_income_gbp_by_asset'][name] + raw['balancing_income_gbp_by_asset'][name] for name in assets}
    agent_residual = math.fsum(abs(asset_market_cash[name] - expected_cash[name]) for name in assets)
    legacy = raw['legacy_downward_fee_gbp_by_asset']
    legacy_abs = math.fsum(abs(v) for v in legacy.values())
    source_down = raw['raw_source_cost_components']['curtailment'] * .5
    attributed_down = math.fsum((*raw['downward_cash_gbp_by_asset'].values(), *legacy.values()))
    down_residual = source_down - attributed_down
    if (abs(cash_residual) > 1e-7
        or any(not math.isclose(asset_market_cash[name], expected_cash[name], rel_tol=1e-12, abs_tol=1e-7) for name in assets)
        or not math.isclose(source_down, attributed_down, rel_tol=1e-12, abs_tol=1e-7)):
        raise ValueError('Period settlement does not reconcile')
    return dict(schema_version='value.doctoral-settlement-details/v1',
        input_sha256=raw['input_sha256'], ahead_sha256=raw['ahead_sha256'],
        absolute_period=outcome.next_state.next_absolute_period-1,
        year=outcome.next_state.year, period_index=outcome.next_state.next_period_index-1,
        cost_profile=COST_PROFILE, settlement_rule=SETTLEMENT_RULE,
        units={'quantity':'MWh/half-hour', 'price':'GBP/MWh', 'cash':'GBP'},
        assets=rows, transactions=transactions, cash_balance_residual_gbp=cash_residual,
        agent_income_residual_gbp=agent_residual, raw_downward_attribution_residual_gbp=down_residual,
        legacy_downward_closed=legacy_abs <= 1e-7,
        legacy_downward_fee_gbp_by_asset=legacy,
        boundaries=['Physical fuel/carbon/other components partition existing operating cost, not additional payments.',
            'Source startup bid adder retained; actual startup expenditure and thesis-unit mapping remain unresolved.',
            'Configured signed downward price retained; no automatic negation or fuel/efficiency recalibration.',
            'Nuclear legacy charges and nonzero legacy VRE offers are not credited as new agent income.',
            'External imports are already in generation and balancing; procurement is not another balancing payment.',
            'No CfD, no storage opportunity compensation, no new nuclear constraint.'])


def publish_settlement_report(root: Path, outcome) -> dict:
    """One atomic, immutable period file; no growing in-memory annual detail."""
    report = settlement_report(outcome)
    data = (json.dumps(report, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(',', ':'))+'\n').encode('utf-8')
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    filename = f"{report['period_index']:05d}.json"
    target = root / filename
    if target.exists():
        if target.read_bytes() != data:
            raise ValueError('Existing settlement detail differs from replay; use a new output directory')
    else:
        fd, name = tempfile.mkstemp(prefix='.settlement-', suffix='.tmp', dir=root)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, target)
        finally:
            if os.path.exists(name):
                os.unlink(name)
    return {'file': filename, 'sha256': hashlib.sha256(data).hexdigest()}


def verify_settlement_files(root: Path, records: list, period_count: int) -> None:
    if len(records) != period_count:
        raise ValueError('Incomplete settlement detail prefix')
    for index, row in enumerate(records):
        if set(row) != {'file', 'sha256'} or row['file'] != f'{index:05d}.json':
            raise ValueError('Invalid settlement detail identity')
        path = Path(root) / row['file']
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != row['sha256']:
            raise ValueError('Settlement detail missing or hash mismatch')
