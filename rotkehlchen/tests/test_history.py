import os

import pytest

from rotkehlchen.assets.asset import Asset
from rotkehlchen.constants.assets import A_ETH
from rotkehlchen.errors import HistoryCacheInvalid
from rotkehlchen.exchanges.data_structures import AssetMovement, Trade
from rotkehlchen.fval import FVal
from rotkehlchen.history import (
    ASSETMOVEMENTS_HISTORYFILE,
    ETHEREUM_TX_LOGFILE,
    LOANS_HISTORYFILE,
    TRADES_HISTORYFILE,
    limit_trade_list_to_period,
)
from rotkehlchen.tests.utils.history import TEST_END_TS, mock_history_processing_and_exchanges
from rotkehlchen.typing import Exchange, TradeType


@pytest.mark.parametrize('use_clean_caching_directory', [True])
def test_history_creation(
        rotkehlchen_server_with_exchanges,
        accountant,
):
    """This is a big test that contacts all exchange mocks and returns mocked
    trades and other data from exchanges in order to create the accounting history
    for a specific period and see that rotkehlchen handles the creation of that
    history correctly"""
    server = rotkehlchen_server_with_exchanges
    rotki = server.rotkehlchen
    rotki.accountant = accountant

    kraken = rotki.exchange_manager.connected_exchanges['kraken']
    kraken.random_trade_data = False
    kraken.random_ledgers_data = False
    (
        accountant_patch,
        polo_patch,
        binance_patch,
        bittrex_patch,
        bitmex_patch,
    ) = mock_history_processing_and_exchanges(rotki)
    with accountant_patch, polo_patch, binance_patch, bittrex_patch, bitmex_patch:
        response = server.process_trade_history(start_ts='0', end_ts=str(TEST_END_TS))
    # The history processing is completely mocked away and omitted in this test.
    # because it is only for the history creation not its processing.
    # For history processing tests look at test_accounting.py and
    # test_accounting_events.py
    assert response['message'] == ''
    assert response['result'] == {}

    # And now make sure that warnings have also been generated for the query of
    # the unsupported/unknown assets
    warnings = rotki.msg_aggregator.consume_warnings()
    assert len(warnings) == 13
    assert 'kraken trade with unknown asset IDONTEXISTTOO' in warnings[0]
    assert 'unknown kraken asset IDONTEXIST. Ignoring its deposit/withdrawals query' in warnings[1]
    msg = 'unknown kraken asset IDONTEXISTEITHER. Ignoring its deposit/withdrawals query'
    assert msg in warnings[2]
    assert 'poloniex trade with unknown asset NOEXISTINGASSET' in warnings[3]
    assert 'poloniex trade with unsupported asset BALLS' in warnings[4]
    assert 'withdrawal of unknown poloniex asset IDONTEXIST' in warnings[5]
    assert 'withdrawal of unsupported poloniex asset DIS' in warnings[6]
    assert 'deposit of unknown poloniex asset IDONTEXIST' in warnings[7]
    assert 'deposit of unsupported poloniex asset EBT' in warnings[8]
    assert 'poloniex loan with unsupported asset BDC' in warnings[9]
    assert 'poloniex loan with unknown asset NOTEXISTINGASSET' in warnings[10]
    assert 'bittrex trade with unsupported asset PTON' in warnings[11]
    assert 'bittrex trade with unknown asset IDONTEXIST' in warnings[12]

    errors = rotki.msg_aggregator.consume_errors()
    assert len(errors) == 3
    assert 'kraken trade with unprocessable pair IDONTEXISTZEUR' in errors[0]
    assert 'kraken trade with unprocessable pair %$#%$#%$#%$#%$#%' in errors[1]
    assert 'bittrex trade with unprocessable pair %$#%$#%#$%' in errors[2]


@pytest.mark.parametrize('use_clean_caching_directory', [True])
def test_history_creation_remote_errors(
        rotkehlchen_server_with_exchanges,
        accountant,
):
    """Test that during history creation, remote errors are detected and errors are returned"""
    server = rotkehlchen_server_with_exchanges
    rotki = server.rotkehlchen
    rotki.accountant = accountant
    kraken = rotki.exchange_manager.connected_exchanges['kraken']
    kraken.random_trade_data = False
    kraken.random_ledgers_data = False
    kraken.remote_errors = True
    (
        accountant_patch,
        polo_patch,
        binance_patch,
        bittrex_patch,
        bitmex_patch,
    ) = mock_history_processing_and_exchanges(rotki, remote_errors=True)
    with accountant_patch, polo_patch, binance_patch, bittrex_patch, bitmex_patch:
        response = server.process_trade_history(start_ts='0', end_ts=str(TEST_END_TS))
    # The history processing is completely mocked away and omitted in this test.
    # because it is only for the history creation not its processing.
    # For history processing tests look at test_accounting.py and
    # test_accounting_events.py
    assert 'invalid JSON' in response['message']
    assert 'Binance' in response['message']
    assert 'Bittrex' in response['message']
    assert 'Bitmex' in response['message']
    assert 'Kraken' in response['message']
    assert 'Poloniex' in response['message']
    assert response['result'] == {}


@pytest.mark.parametrize('use_clean_caching_directory', [True])
def test_history_creation_corrupt_trades_cache(
        rotkehlchen_server_with_exchanges,
        accountant,
        accounting_data_dir,
):
    """
    Tests for corrupt trade cache.

    Test that if cache is used and data are corrupt we revert to omitting
    cache and contacting the exchanges
    """

    # Create the "broken" trades cache. Must have broken cache for all registered exchanges too
    historyfile_path = os.path.join(accounting_data_dir, TRADES_HISTORYFILE)
    with open(historyfile_path, 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": '
            f'[{{"unknown_trade_key": "random_trade_value"}}]}}',
        )
    with open(os.path.join(accounting_data_dir, 'poloniex_trades.json'), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": '
            f'{{"BTC_SJX": [{{"unknown_trade_key": "random_trade_value"}}]}}}}',
        )
    with open(os.path.join(accounting_data_dir, 'kraken_trades.json'), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": '
            f'[{{"unknown_trade_key": "random_trade_value"}}]}}',
        )
    with open(os.path.join(accounting_data_dir, 'binance_trades.json'), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": '
            f'[{{"unknown_trade_key": "random_trade_value"}}]}}',
        )
    with open(os.path.join(accounting_data_dir, 'bittrex_trades.json'), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": '
            f'[{{"unknown_trade_key": "random_trade_value"}}]}}',
        )
    with open(os.path.join(accounting_data_dir, LOANS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": '
            f'[{{"unknown_trade_key": "random_trade_value"}}]}}',
        )
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": '
            f'[]}}',
        )
    with open(os.path.join(accounting_data_dir, ETHEREUM_TX_LOGFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": '
            f'[]}}',
        )

    server = rotkehlchen_server_with_exchanges
    rotki = server.rotkehlchen
    rotki.accountant = accountant
    kraken = rotki.exchange_manager.connected_exchanges['kraken']
    kraken.random_trade_data = False
    kraken.random_ledgers_data = False
    (
        accountant_patch,
        polo_patch,
        binance_patch,
        bittrex_patch,
        bitmex_patch,
    ) = mock_history_processing_and_exchanges(rotki)
    with accountant_patch, polo_patch, binance_patch, bittrex_patch, bitmex_patch:
        response = server.process_trade_history(start_ts='0', end_ts=str(TEST_END_TS))
    # The history processing is completely mocked away and omitted in this test.
    # because it is only for the history creation not its processing.
    # For history processing tests look at test_accounting.py and
    # test_accounting_events.py
    assert response['message'] == ''
    assert response['result'] == {}

    # And now make sure that warnings/errors number did not change
    warnings = rotki.msg_aggregator.consume_warnings()
    assert len(warnings) == 13
    errors = rotki.msg_aggregator.consume_errors()
    assert len(errors) == 3


def test_limit_trade_list_to_period():
    trade1 = Trade(
        timestamp=1459427707,
        location='kraken',
        pair='ETH_BTC',
        trade_type=TradeType.BUY,
        amount=FVal(1),
        rate=FVal(1),
        fee=FVal('0.1'),
        fee_currency=A_ETH,
    )
    trade2 = Trade(
        timestamp=1469427707,
        location='poloniex',
        pair='ETH_BTC',
        trade_type=TradeType.BUY,
        amount=FVal(1),
        rate=FVal(1),
        fee=FVal('0.1'),
        fee_currency=A_ETH,
    )
    trade3 = Trade(
        timestamp=1479427707,
        location='poloniex',
        pair='ETH_BTC',
        trade_type=TradeType.BUY,
        amount=FVal(1),
        rate=FVal(1),
        fee=FVal('0.1'),
        fee_currency=A_ETH,
    )

    full_list = [trade1, trade2, trade3]
    assert limit_trade_list_to_period(full_list, 1459427706, 1479427708) == full_list
    assert limit_trade_list_to_period(full_list, 1459427707, 1479427708) == full_list
    assert limit_trade_list_to_period(full_list, 1459427707, 1479427707) == full_list

    expected = [trade2, trade3]
    assert limit_trade_list_to_period(full_list, 1459427708, 1479427707) == expected
    expected = [trade2]
    assert limit_trade_list_to_period(full_list, 1459427708, 1479427706) == expected
    assert limit_trade_list_to_period(full_list, 0, 10) == []
    assert limit_trade_list_to_period(full_list, 1479427708, 1479427719) == []
    assert limit_trade_list_to_period([trade1], 1459427707, 1459427707) == [trade1]
    assert limit_trade_list_to_period([trade2], 1469427707, 1469427707) == [trade2]
    assert limit_trade_list_to_period([trade3], 1479427707, 1479427707) == [trade3]
    assert limit_trade_list_to_period(full_list, 1459427707, 1459427707) == [trade1]
    assert limit_trade_list_to_period(full_list, 1469427707, 1469427707) == [trade2]
    assert limit_trade_list_to_period(full_list, 1479427707, 1479427707) == [trade3]


def test_assets_movements_from_cache(accounting_data_dir, trades_historian):
    """
    Test that when reading asset movements from a file and we get a dictlist it
    is properly turned into an AssetMovement
    """
    data_str = (
        f'[{{"exchange": "kraken", "category": "deposit", "timestamp": 1520938730, '
        f'"asset": "KFEE", "amount": "100.0", "fee": "0.0"}}, {{"exchange": "poloniex",'
        f'"category": "withdrawal", "timestamp": 1510938730, "asset": "BTC", '
        f'"amount": "2.5", "fee": "0.00001"}}]'
    )
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {data_str}}}',
        )

    asset_movements = trades_historian._get_cached_asset_movements(
        start_ts=0,
        end_ts=TEST_END_TS,
        end_at_least_ts=TEST_END_TS,
    )
    assert len(asset_movements) == 2
    assert isinstance(asset_movements[0], AssetMovement)
    assert asset_movements[0].exchange == Exchange.KRAKEN
    assert asset_movements[0].category == 'deposit'
    assert asset_movements[0].timestamp == 1520938730
    assert isinstance(asset_movements[0].asset, Asset)
    assert asset_movements[0].asset == Asset('KFEE')
    assert asset_movements[0].amount == FVal('100')
    assert asset_movements[0].fee == FVal('0')

    assert isinstance(asset_movements[1], AssetMovement)
    assert asset_movements[1].exchange == Exchange.POLONIEX
    assert asset_movements[1].category == 'withdrawal'
    assert asset_movements[1].timestamp == 1510938730
    assert isinstance(asset_movements[1].asset, Asset)
    assert asset_movements[1].asset == Asset('BTC')
    assert asset_movements[1].amount == FVal('2.5')
    assert asset_movements[1].fee == FVal('0.00001')


def test_assets_movements_from_invalid_cache(accounting_data_dir, trades_historian):
    """
    Test that when reading asset movements from a file with invalid entries it is
    handled properly by raising a HistoryCacheInvalid error
    """
    data_str = (
        '[{"exchange": "kraken", "category": "deposit", "timestamp": 1520938730, '
        '"asset": "KFEE", "amount": "100.0", "fee": "0.0"}]'
    )
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {data_str}}}',
        )

    # first of all see that it all works fine with valid entries
    asset_movements = trades_historian._get_cached_asset_movements(
        start_ts=0,
        end_ts=TEST_END_TS,
        end_at_least_ts=TEST_END_TS,
    )
    # The specifics of proper deserialization are checked in test_assets_movements_from_cache
    assert len(asset_movements) == 1

    # test for unknown exchange name
    test_str = data_str.replace('kraken', 'unknownexchange')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )

    # test for invalid category
    test_str = data_str.replace('deposit', 'brodown')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )

    # test for invalid category
    test_str = data_str.replace('deposit', 'brodown')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )

    # test for invalid timestamp
    test_str = data_str.replace('1520938730', '"timestampshouldnotbestring"')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )

    # test for invalid asset entry
    test_str = data_str.replace('"KFEE"', '[]')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )

    # test for unknown asset entry
    test_str = data_str.replace('"KFEE"', '"DSADSAD"')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )

    # test for invalid fee
    test_str = data_str.replace('"0.0"', '"dasdsadsad"')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )

    # test for invalid amount
    test_str = data_str.replace('"100.0"', 'null')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )

    # test for missing key
    test_str = data_str.replace('"category": "deposit",', '')
    with open(os.path.join(accounting_data_dir, ASSETMOVEMENTS_HISTORYFILE), 'w') as f:
        f.write(
            f'{{"start_time":0, "end_time": {TEST_END_TS}, "data": {test_str}}}',
        )
    with pytest.raises(HistoryCacheInvalid):
        asset_movements = trades_historian._get_cached_asset_movements(
            start_ts=0,
            end_ts=TEST_END_TS,
            end_at_least_ts=TEST_END_TS,
        )
