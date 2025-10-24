import textwrap
from gemini_supply.preferences import NormalizedItem, PreferenceRecord


def build_shopper_prompt(
  item_name: str,
  normalized: NormalizedItem,
  preference: PreferenceRecord | None,
  specific_request: bool,
) -> str:
  if preference is not None:
    item_name = f"{normalized.quantity}x {preference.product_name}"

  # Case 2: No preference - search and decide
  return textwrap.dedent(f"""
    Product to add: {item_name}

    Context:
    The "Product to add" is text from a human-written shopping list. Expect:
    - Informal/shorthand writing (e.g., "whole milk" instead of "Organic 3.25% Milk 2L")
    - Missing details (brand, size, quantity units)
    - Typos or ambiguous terms

    Your Goal:
    Find a product that matches the user's intent, then add the item in the correct quantity to the shopping cart.

    OR (if unable to do the above):
    Collect thoughtful alternative products for the user to consider.

    IMPORTANT: All product interactions happen on the search results page. Product detail pages
    contain no additional information and no additional functionality - everything you need is
    in the search results. Do not attempt to navigate to individual product pages.

    Instructions:

    1. Locate the search box at the top of metro.ca
      a. Determine appropriate search terms:
          - Extract the core product name/type from "{item_name}"
          - Use terms that would appear in a product name or description
          - Examples:
            * "whole milk" → search "whole milk"
            * "milk for cereal" → search "milk"
            * "something to spread on toast" → search "butter" or "jam"
            * "2L homo" → search "homogenized milk"
      b. Type the search terms into the search box
      c. Press Enter or click the search button
      d. Wait for the search results page to load

    2. Examine search results systematically:

      a. SCROLLING GUIDELINES:
          - Scrolling keeps you on the same page - you won't accidentally navigate away
          - If you see products that don't match your search, it's because the site's search
            quality is poor, not because you changed pages

      b. SCAN PHASE: Scroll through the first 5-10 results, noting:
          - Are there exact/close matches to "{item_name}"?
          - What's the quality distribution? (relevant → somewhat related → irrelevant)
          - Note: Search results often have a "long tail" of poor matches. This is normal.

      c. MATCHING CRITERIA (in priority order):
          i.   Product name contains the key terms from "{item_name}"
          ii.  Appropriate category (if milk requested, don't pick cheese)
          iii. Reasonable size/quantity for the item type
          iv.  Well-known brands are safer choices when ambiguous
          v.   Price seems reasonable for the product type

      d. CONFIDENCE DECISION:
          - HIGH CONFIDENCE (proceed to step 3):
            * One result clearly matches all key terms
            * OR: Multiple results are essentially the same product (different sizes/brands
              of the same thing, and any would work)

          - LOW CONFIDENCE (call request_product_choice):
            * Multiple distinct product types could match (e.g., "milk" → whole/skim/almond/oat)
            * Ambiguous size/quantity (e.g., "eggs" → 6/12/18 pack?)
            * Item name is vague or has multiple interpretations

            When calling request_product_choice:
            - Include up to 10 DIVERSE, REASONABLE options (skip the long tail of bad results)
            - For each: title, price_text
            - Prioritize options that differ meaningfully (different brands, sizes, types)
            - Exclude near-duplicates unless size variation matters

          - WHEN YOU HAVE MULTIPLE SIMILAR OPTIONS:
            Ask yourself:
            - Is this a distinction the user cares about? (whole vs. skim milk: YES.
              Brand A vs. Brand B same milk: MAYBE NOT)
            - Would a typical shopper need to choose, or is any variant acceptable?
            - If unsure → request_product_choice. Better to ask than guess wrong.

      e. HANDLING ProductDecision RESPONSE:
          The response will have a 'decision' field:
          * If decision="selected": Locate the product from 'selected_choice' in the search
            results, then proceed to step 3.
          * If decision="alternate": The user provided new text in 'alternate_text'.
            Search for this alternate text instead.
            If the alternate includes a quantity (e.g., "3 whole milk"), use that quantity.
            Otherwise, keep the original quantity.
            Start over from step 1 with the new search term.

    3. On the search results page, interact with the chosen product:

      - If you see a shopping cart icon button (🛒):
        * Click the 🛒 button
        * 🚨VERY IMPORTANT🚨 If the "Delivery or Pickup?" form appears:
          1. Fill in the postal code: M4C1Y5
          2. Press "Confirm"
          3. Several delivery or pickup options will appear. Click the LAST option: "Choose Later"
          4. The quantity controls will now be visible with a quantity of 1
          5. Adjust to the desired quantity using the plus button if needed
        * Proceed to step 4

      - If you see quantity controls (trash icon, quantity number, plus button):
        * Note the current quantity shown
        * Adjust to the desired quantity using the plus button
        * Proceed to step 4

      - If you realize you've added the WRONG item:
        * Use the trash icon to remove the incorrect item
        * Return to step 2 to find the correct product

    4. Verify success:
      ✓ Quantity controls (trash icon, quantity number, plus button) are visible
      ✓ The quantity shown matches the requested amount

      If either check fails:
      - Look for error messages
      - Try clicking the 🛒 button ONE more time
      - If still failing, call report_item_not_found with specific error details

    5. Call report_item_added(item_name, price_text, quantity) when successful.
      - The 'quantity' parameter should be the DIFFERENCE applied (how many items were added)
        * If the product wasn't in cart and you added 3: quantity=3
        * If the product had 2 in cart and you adjusted to 5: quantity=3
        * If the product had 3 in cart and you kept it at 3: quantity=0
        * This can be 0 if the desired quantity was already in the cart

    6. If product cannot be located after reasonable attempts, call report_item_not_found(item_name, explanation).

    Error Recovery:
    If at any point you become disoriented:
    - Identify what page you're on (search results? something else?)
    - Check the URL bar to confirm location
    - If you need to return to search results: Don't use the back button (it's unreliable).
      Instead, search again using step 1.
    - If completely lost: call report_item_not_found with explanation

    Self-Correction Checks:
    If you notice you're seeing mostly irrelevant results, the search term may be too vague.
    Consider calling request_product_choice with explanation.

    If you realize you've added the WRONG item to the cart:
    - Use the trash icon to remove the incorrect item
    - Then search for and add the correct item
    - Only call report_item_added after the correct item is in the cart

    Constraints:
    - Stay on metro.ca and allowed resources only.
    - Do NOT navigate to checkout, payment, or account pages.
    - Focus solely on adding the requested item.
    - REMEMBER the delivery/pickup flow: postal code M4C1Y5 → Confirm → Choose Later
    """)
