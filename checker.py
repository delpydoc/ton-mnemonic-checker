import os
import re
import time
from pprint import pprint
from typing import Optional

import requests
from pytonapi import Tonapi
from tonsdk.contract import Contract
from tonsdk.contract.wallet import Wallets, WalletVersionEnum
from tonsdk.crypto.bip39._english import words

IGNORE_WALLET_VERSIONS = [_v.strip() for _v in os.environ.get('IGNORE_WALLET_VERSIONS', 'v2r1, v2r2, hv2').split(',') if _v.strip()]
SUPPORTED_WALLET_IDS = [int(ch) for ch in os.getenv('SUPPORTED_WALLET_IDS', '698983191, ').split(',') if ch.isdigit()]
TONAPI_KEY = os.getenv('TONAPI_KEY', '')  # or input("Enter TONAPI_KEY: ")
TONCENTER_HOST = os.getenv('TONCENTER_HOST', 'https://toncenter.com/api/v2')
TONCENTER_API_KEY = os.getenv('TONCENTER_API_KEY')
FREE_TIER_DELAY = float(os.getenv('FREE_TIER_DELAY', '4'))

tonapi = Tonapi(TONAPI_KEY, headers={} if TONAPI_KEY else {'User-Agent': 'ton_mnemonic_checker'})


def free_tier_delay():
    if FREE_TIER_DELAY >= 1:
        print(f"[*] Free tier delay: {FREE_TIER_DELAY} seconds (set custom value via FREE_TIER_DELAY env var)")
        time.sleep(FREE_TIER_DELAY)


def get_wallet_funds(wallet: Contract) -> dict:
    wallet_address = wallet.address.to_string(1, 1, 1)
    funds = {
        'jettons': {},
        'nfts': {}
    }
    free_tier_delay()
    for nft in (tonapi.accounts.get_nfts(wallet_address)).nft_items:
        nft_address = nft.address.to_userfriendly(is_bounceable=False)
        funds['nfts'][nft_address] = {
            'metadata': nft.metadata or {},
        }

    tc_authorization = {}
    if TONCENTER_API_KEY:
        tc_authorization['api_key'] = TONCENTER_API_KEY

    tc_response = requests.get(
        f'{TONCENTER_HOST}/getAddressBalance',
        params={**tc_authorization, 'address': wallet_address},
    ).json()

    try:
        ton_balance = int(tc_response['result'])
    except:
        print(tc_response)
        ton_balance = 0

    funds['jettons']['0:0'] = {
        'symbol': 'TON',
        'balance': ton_balance,
        'decimals': 9,
        'name': 'TON',
        'wallet_address': ''
    }

    free_tier_delay()
    for jetton_balance in (tonapi.accounts.get_jettons_balances(wallet_address)).balances:
        if int(jetton_balance.balance or 0) > 0:
            jetton = jetton_balance.jetton
            jetton_address = jetton.address.to_userfriendly(is_bounceable=False)
            funds['jettons'][jetton_address] = {
                'symbol': jetton.symbol or "REALLY_UNKNOWN_SYMBOL",
                'balance': int(jetton_balance.balance or 0),
                'decimals': int(jetton.decimals or 9),

                'name': jetton.name or "REALLY_UNKNOWN_NAME",
                'wallet_address': jetton_balance.wallet_address.address.to_userfriendly(is_bounceable=False),
            }

    return funds


def get_mnemonic_funds(mnemonic: list) -> dict:
    funds = {}
    for wallet_version in WalletVersionEnum:
        if wallet_version.value in IGNORE_WALLET_VERSIONS:
            continue

        for wallet_id in SUPPORTED_WALLET_IDS:
            print(f"[!] Checking wallet {wallet_version.value} {wallet_id}...")
            _, _, _, wallet = Wallets.from_mnemonics(mnemonic, version=wallet_version, wallet_id=wallet_id)
            funds[f"{wallet_version.value}:{wallet_id}:{' '.join(mnemonic)}:{wallet.address.to_string(1, 1, 1)}"] = get_wallet_funds(wallet)

    return funds


def extract_elements(src: list) -> list:
    elements = []
    for word in src:
        word = word.strip()
        if word:
            elements.append(word)

    return elements


def extract_mnemonic_from_plain_text(text) -> Optional[list]:
    text = text.strip()
    elements = []
    f_complete = {}
    p_index = None
    for word in extract_elements(text.split('\n')):
        if p_index:
            word = word.split(' ')[0]
            if word in words:
                f_complete[p_index] = word
                p_index = None

        if re.match(r'^\d+\s*\.\s*[a-zA-Z]+$', word):
            index, word = word.split('.')
            word = word.strip()
            if word in words:
                index = int(index)
                f_complete[index] = word
                p_index = None
        elif re.match(r'^\d+\s*\.+', word):
            p_index = int(word.split('.')[0])
        else:
            p_index = None

        elements.append(word)

    if len(f_complete) in [24]:
        try:
            return [f_complete[index] for index in range(1, 25)]
        except KeyError:
            pass

    mnemonic = []
    for word in elements:
        for part in extract_elements(word.split(' ')):
            for part_2 in extract_elements(part.split('.')):
                part_2 = part_2.strip()
                part_2 = part_2.lower()
                if part_2 and part_2 in words:
                    mnemonic.append(part)

    if not (len(mnemonic) in [24]):
        print(f"""[?] Extracted mnemonic phrase is not valid
Reference: {mnemonic}""")
        return main()

    return mnemonic


def print_mnemonic_funds(mnemonic: list) -> None:
    funds = get_mnemonic_funds(mnemonic)
    for wallet_constructor, wallet_funds in funds.items():
        (wallet_version, wallet_id, wallet_mnemonic, wallet_address) = wallet_constructor.split(':')
        wallet_id = int(wallet_id)
        wallet_mnemonic = wallet_mnemonic.split(' ')
        print(f"[+] Wallet {wallet_version} {wallet_id} {wallet_mnemonic[0]}-{wallet_mnemonic[-1]}")
        print(f"https://tonscan.org/address/{wallet_address}")
        for jetton_address, jetton_funds in wallet_funds['jettons'].items():
            if jetton_address == '0:0':
                jetton_name = 'Account balance'
            else:
                jetton_name = f"""Jetton{f'{jetton_funds["name"]} ' if jetton_funds.get('name') else ''} {jetton_address}"""

            jetton_friendly_balance = jetton_funds['balance'] / (10 ** jetton_funds.get('decimals', 9))
            print(f"""    [+] {jetton_name}: {jetton_friendly_balance:.6f} {jetton_funds['symbol'].upper()}""")

        for nft_address, nft_desc in wallet_funds['nfts'].items():
            print(f"    [+] NFT {nft_address}:")
            pprint(nft_desc['metadata'])

    return main()


def main():
    print(f"""[?] Please, enter plain text & input 0 for start working with it:""")
    plain_text = ""
    while True:
        new_input = input()
        if new_input == '0':
            break

        plain_text += new_input + '\n'

    mnemonic = extract_mnemonic_from_plain_text(plain_text)
    print(f"""[!] Extracted mnemonic phrase: {' '.join(mnemonic)}""")
    return print_mnemonic_funds(mnemonic)


if __name__ == '__main__':
    main()
