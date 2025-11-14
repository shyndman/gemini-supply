# Research: Image Display Options in Telegram

I've researched the various ways to display product images in Telegram using python-telegram-bot v22.5. Here's a comprehensive analysis of the options:

## Available Telegram Bot API Methods

### 1. **send_photo()** - Single Image with Inline Buttons ⭐
Sends one image with a caption and can attach inline keyboard buttons directly.

**How it works:**
- Photo can be a URL, file path, bytes, or file object
- Caption supports up to 1024 characters with MarkdownV2/HTML formatting
- `reply_markup` parameter accepts `InlineKeyboardMarkup` (our current button layout works!)
- Image displays inline in the chat

**Pros:**
- ✅ Simple and direct implementation
- ✅ Buttons attach directly to the photo message
- ✅ Supports rich caption formatting
- ✅ Best integration with existing code

**Cons:**
- ❌ Only one image per message
- ❌ Multiple products require multiple messages (may clutter chat)
- ❌ Could trigger rate limits if sending many sequential photos

**Best for:** Showing one primary product image with selection options

---

### 2. **send_media_group()** - Multiple Images as Album
Sends 2-10 images as a grouped album/gallery view.

**How it works:**
- Accepts sequence of `InputMediaPhoto` objects
- Each image can have its own caption
- Creates compact album layout in Telegram

**Pros:**
- ✅ Clean visual presentation (gallery view)
- ✅ All images load together
- ✅ Great for side-by-side product comparison
- ✅ Compact message footprint (2-10 images in one unit)

**Cons:**
- ❌ **CRITICAL: Cannot attach inline keyboard buttons** (Telegram API limitation)
- ❌ Requires separate message for buttons (creates disconnect)
- ❌ Max 10 items per media group
- ❌ More complex to correlate button numbers with images

**Best for:** Visual comparison when buttons can be in a follow-up message

---

### 3. **Inline URL Buttons** - Links to Images
Send text-only message with URL buttons that link to external product images.

**How it works:**
- Current text-based message format
- Add URL-type inline buttons (e.g., "🖼️ View Photo")
- User taps to open image in browser/web preview

**Pros:**
- ✅ Minimal changes to current implementation
- ✅ Single message (no clutter)
- ✅ Low bandwidth usage
- ✅ No rate limit concerns

**Cons:**
- ❌ No inline image preview in chat
- ❌ Requires external tap (interrupts flow)
- ❌ Depends on external image hosting (merchant CDN reliability)
- ❌ Poor UX compared to inline images

**Best for:** Quick fallback option or when bandwidth is a concern

---

### 4. **Sequential Photos** - One Photo Per Product
Send individual `send_photo()` call for each product choice.

**How it works:**
- Loop through products, sending photo + caption + buttons for each
- Each product gets its own message with its own selection buttons
- Alternative: Send all photos, then one consolidated button message

**Pros:**
- ✅ Clear visual separation per product
- ✅ Each product gets full image treatment
- ✅ Can attach buttons to each photo (variant 1)

**Cons:**
- ❌ Creates many messages (clutters chat history significantly)
- ❌ Difficult to compare products side-by-side
- ❌ High risk of hitting Telegram rate limits (~30 msg/sec groups, lenient for private)
- ❌ User needs to scroll through multiple messages

**Best for:** When products are very different and need individual focus

---

### 5. **Hybrid: Media Group + Button Message**
Combines album view with separate button message.

**How it works:**
1. Send `send_media_group()` with all product images (numbered captions)
2. Send follow-up text message with buttons and detailed product info
3. Text explains "Photos above correspond to options 1-5..."

**Pros:**
- ✅ Best visual presentation (album view)
- ✅ All images visible at once for comparison
- ✅ Only 2 messages total (reasonable clutter)
- ✅ Maintains current button interaction pattern

**Cons:**
- ❌ Buttons separated from images (requires mental mapping)
- ❌ Max 10 products per group
- ❌ Medium implementation complexity

**Best for:** Production implementation with good UX balance

---

## Telegram API Constraints

### Rate Limits
- Private chats: ~30 messages/second (lenient in practice)
- Group chats: ~20 messages/second
- **Impact:** Sequential photo approach needs throttling

### File Size & Format
- Photos: Max 10MB (sent as document), 5MB (sent as photo with auto-compression)
- Telegram auto-compresses photos (can preserve quality by sending as document)
- **Recommendation:** Use URLs to merchant-hosted images when possible

### Button & Caption Limits
- Inline keyboard: Max ~100 buttons (soft limit), 8 per row (6 recommended for mobile)
- Photo captions: 1024 characters max
- Regular messages: 4096 characters max
- Callback data: 64 bytes max
- **Current implementation:** 2 buttons per product = ✅ well within limits

---

## Recommended Implementation Strategy

### **Phase 1: MVP - Media Group + Button Message** (Recommended) 

**Approach:**
1. Send `send_media_group()` with product images (up to 10)
2. Each image caption: `"1. [Product Title] - $X.XX"`
3. Follow with text message containing current detailed text + inline keyboard
4. Fallback to text-only if images unavailable

**Why this approach:**
- ✅ Best visual experience for product comparison
- ✅ Clean album presentation
- ✅ Maintains current button interaction (select/star pattern)
- ✅ Handles missing images gracefully
- ✅ Reasonable implementation effort

**Implementation checklist:**
- [ ] Add `image_url: HttpUrl | None` field to `ProductChoice` model (using pydantic's HttpUrl for validation)
- [ ] Update agent scraper to extract image URLs from product listings
- [ ] Add `_send_media_group_prompt()` method to `TelegramPreferenceMessenger`
- [ ] Modify `_send_prompt()` to check for images and choose appropriate send method
- [ ] Update caption formatting for numbered image captions
- [ ] Add error handling for failed image fetches (fallback to text-only)
- [ ] Update tests for new message flow

---

### **Phase 2: Optimization** (After MVP validation)

Based on user feedback, consider:
- **Smart grouping:** If >10 products, send multiple albums with paginated buttons
- **Image caching:** Store frequently-used images on our CDN to avoid merchant URL issues
- **Thumbnail generation:** Create smaller thumbnails for faster loading
- **Hybrid fallback:** Single representative photo if media group fails

---

### **Alternative: Quick Win - Single Photo**

If Phase 1 scope is too large, start with:
1. Send single `send_photo()` with first product image
2. Keep current text message with all product details + buttons
3. Add optional URL buttons: "🖼️ View Other Options"

**Pros:** Minimal changes, immediate visual feedback
**Cons:** Not as impactful, only shows one image

---

## Code Impact Areas

### Files to Modify:
1. **`src/generative_supply/preferences/types.py`**
   - Add `image_url: HttpUrl | None` field to `ProductChoice` (pydantic's HttpUrl for validation)
   - Add optional `image_alt_text: str | None` for accessibility
   - Note: HttpUrl needs to be imported from `pydantic` (already used in codebase)

2. **`src/generative_supply/preferences/messenger.py`**
   - Add `_send_media_group_prompt()` method
   - Update `_send_prompt()` with image detection logic
   - Add `_format_image_caption()` for numbered captions
   - Add error handling for image fetch failures

3. **Agent scraper** (wherever ProductChoice is created)
   - Extract `<img>` URLs from product listings
   - Validate image URLs are accessible
   - Handle missing images gracefully

4. **Tests**
   - Update `test_preferences_behavior.py` with image scenarios
   - Mock image URL validation
   - Test fallback to text-only mode

---

## Open Questions to Address

1. **Image hosting:** Use merchant CDN directly or cache on our infrastructure?
   - **Recommendation:** Start with merchant URLs, add caching later if reliability issues arise

2. **Missing images:** How to handle products without images?
   - **Recommendation:** Fallback to text-only mode, add placeholder icon, or exclude from image group

3. **Image quality:** Use thumbnail, medium, or full resolution?
   - **Recommendation:** Medium resolution (~800px wide) for good quality + reasonable size

4. **Rate limiting:** Do we need throttling between image sends?
   - **Recommendation:** Media group is one API call, so no throttling needed for MVP

5. **>10 products:** How to handle choice lists exceeding media group limit?
   - **Recommendation:** Send multiple media groups (e.g., "Options 1-10" then "Options 11-15") or top 10 only

---

## References

- **python-telegram-bot library:** https://github.com/python-telegram-bot/python-telegram-bot
- **Library docs:** https://docs.python-telegram-bot.org/
- **Telegram Bot API - sendPhoto:** https://core.telegram.org/bots/api#sendphoto
- **Telegram Bot API - sendMediaGroup:** https://core.telegram.org/bots/api#sendmediagroup
- **Telegram Bot API - InputMediaPhoto:** https://core.telegram.org/bots/api#inputmediaphoto
- **Current implementation:** `src/generative_supply/preferences/messenger.py`

---

Let me know which approach you'd like to pursue, and I can provide more detailed implementation guidance or create a prototype!
