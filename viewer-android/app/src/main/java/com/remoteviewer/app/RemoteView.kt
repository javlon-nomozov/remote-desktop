package com.remoteviewer.app

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Paint
import android.graphics.Rect
import android.util.AttributeSet
import android.view.MotionEvent
import android.view.View
import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.abs

/**
 * Server ekranini chizadi va teginishlarni input hodisalariga aylantiradi.
 *
 * Barmoqlar soni bo'yicha ikki yo'l:
 *  - 1-2 barmoq (touchscreen rejim): har bir barmoq `touch` kontakt sifatida yuboriladi —
 *    server haqiqiy multi-touch injekt qiladi (pinch-zoom, 2-barmoq scroll native ishlaydi).
 *  - 3-4 barmoq: swipe sifatida aniqlanadi va `gesture` buyrug'i yuboriladi (server Windows
 *    tugma kombinatsiyasiga map qiladi: 4-barmoq L/R -> oyna almashtirish, 3-barmoq yuqoriga
 *    -> Task View, va h.k.). Bu touchscreen OS-gesturasiga tayanmaydi — ishonchli.
 *
 * touchpad rejimida esa bitta barmoq nisbiy kursor; tap = chap klик.
 */
class RemoteView @JvmOverloads constructor(
    context: Context,
    attrs: AttributeSet? = null,
) : View(context, attrs) {

    var onInput: ((String) -> Unit)? = null
    var touchpadMode: Boolean = false

    private var bitmap: Bitmap? = null
    private val paint = Paint(Paint.FILTER_BITMAP_FLAG)
    private val dst = Rect()

    // touchpad
    private var lastX = 0f
    private var lastY = 0f

    // ko'p barmoqli gestura holati
    private var gestureMode = false
    private var gestureFired = false
    private var maxPointers = 0
    private var startCx = 0f
    private var startCy = 0f
    private var lastCx = 0f
    private var lastCy = 0f
    private val sentIds = HashSet<Int>()  // touchscreen rejimida serverga down yuborilgan idlar

    fun setFrame(bmp: Bitmap) {
        bitmap = bmp
        postInvalidate()
    }

    override fun onDraw(canvas: Canvas) {
        val b = bitmap ?: return
        dst.set(0, 0, width, height)
        canvas.drawBitmap(b, null, dst, paint)
    }

    private fun nx(x: Float): Double = (x / width).coerceIn(0f, 1f).toDouble()
    private fun ny(y: Float): Double = (y / height).coerceIn(0f, 1f).toDouble()

    private fun centroidX(e: MotionEvent): Float {
        var s = 0f
        for (i in 0 until e.pointerCount) s += e.getX(i)
        return s / e.pointerCount
    }

    private fun centroidY(e: MotionEvent): Float {
        var s = 0f
        for (i in 0 until e.pointerCount) s += e.getY(i)
        return s / e.pointerCount
    }

    override fun onTouchEvent(event: MotionEvent): Boolean {
        if (touchpadMode) return handleTouchpad(event)

        val action = event.actionMasked
        val pc = event.pointerCount
        val cx = centroidX(event)
        val cy = centroidY(event)

        when (action) {
            MotionEvent.ACTION_DOWN -> {
                maxPointers = pc
                gestureMode = false
                gestureFired = false
                startCx = cx; startCy = cy; lastCx = cx; lastCy = cy
                sentIds.clear()
            }
            MotionEvent.ACTION_POINTER_DOWN -> {
                if (pc > maxPointers) maxPointers = pc
                if (maxPointers >= 3 && !gestureMode) {
                    releaseSentContacts()   // yuborilgan touch'ni bekor qilamiz (server stuck bo'lmasin)
                    gestureMode = true
                    startCx = cx; startCy = cy
                }
            }
        }

        if (gestureMode) {
            lastCx = cx; lastCy = cy
            if (!gestureFired &&
                (action == MotionEvent.ACTION_POINTER_UP ||
                 action == MotionEvent.ACTION_UP ||
                 action == MotionEvent.ACTION_CANCEL)
            ) {
                fireGesture()
                gestureFired = true
            }
            if (action == MotionEvent.ACTION_UP || action == MotionEvent.ACTION_CANCEL) {
                gestureMode = false
                gestureFired = false
                maxPointers = 0
                sentIds.clear()
            }
            return true
        }

        return handleTouchscreen(event)
    }

    private fun handleTouchscreen(event: MotionEvent): Boolean {
        val action = event.actionMasked
        val changed = event.actionIndex
        val contacts = JSONArray()
        for (i in 0 until event.pointerCount) {
            val id = event.getPointerId(i)
            val state = when (action) {
                MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN ->
                    if (i == changed) "down" else "move"
                MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP ->
                    if (i == changed) "up" else "move"
                MotionEvent.ACTION_CANCEL -> "up"
                else -> "move"
            }
            if (state == "up") sentIds.remove(id) else sentIds.add(id)
            val c = JSONObject()
            c.put("id", id)
            c.put("x", nx(event.getX(i)))
            c.put("y", ny(event.getY(i)))
            c.put("state", state)
            contacts.put(c)
        }
        send(JSONObject().put("t", "touch").put("contacts", contacts))
        return true
    }

    /** Serverga down yuborilgan barcha kontaktlarni "up" qilib bo'shatadi. */
    private fun releaseSentContacts() {
        if (sentIds.isEmpty()) return
        val contacts = JSONArray()
        for (id in sentIds) {
            contacts.put(
                JSONObject().put("id", id).put("x", 0.5).put("y", 0.5).put("state", "up")
            )
        }
        send(JSONObject().put("t", "touch").put("contacts", contacts))
        sentIds.clear()
    }

    private fun fireGesture() {
        val dx = lastCx - startCx
        val dy = lastCy - startCy
        val adx = abs(dx)
        val ady = abs(dy)
        val thresh = 0.06f * if (adx > ady) width else height  // ~6% harakat = swipe
        if (adx < thresh && ady < thresh) return  // swipe emas (ko'p barmoqli tap) -> e'tiborsiz
        val dir = if (adx > ady) (if (dx > 0) "right" else "left")
                  else (if (dy > 0) "down" else "up")
        val name = gestureName(maxPointers, dir) ?: return
        send(JSONObject().put("t", "gesture").put("name", name))
    }

    private fun gestureName(fingers: Int, dir: String): String? = when {
        fingers >= 4 -> when (dir) {
            "left" -> "switch_prev"      // 4-barmoq chapga -> oldingi oyna
            "right" -> "switch_next"     // 4-barmoq o'ngga -> keyingi oyna
            "up" -> "taskview"
            "down" -> "showdesktop"
            else -> null
        }
        fingers == 3 -> when (dir) {
            "up" -> "taskview"           // 3-barmoq yuqoriga -> Task View
            "down" -> "showdesktop"
            "left" -> "desktop_prev"
            "right" -> "desktop_next"
            else -> null
        }
        else -> null
    }

    private fun send(obj: JSONObject) {
        onInput?.invoke(obj.toString())
    }

    private fun handleTouchpad(event: MotionEvent): Boolean {
        when (event.actionMasked) {
            MotionEvent.ACTION_DOWN -> {
                lastX = event.x
                lastY = event.y
            }
            MotionEvent.ACTION_MOVE -> {
                val dx = (event.x - lastX) / width
                val dy = (event.y - lastY) / height
                lastX = event.x
                lastY = event.y
                send(JSONObject().put("t", "mouse").put("dx", dx.toDouble())
                    .put("dy", dy.toDouble()).put("buttons", 0).put("mode", "rel"))
            }
            MotionEvent.ACTION_UP -> {
                // tap -> chap klик
                send(JSONObject().put("t", "mouse").put("dx", 0.0).put("dy", 0.0)
                    .put("buttons", 1).put("mode", "rel"))
                send(JSONObject().put("t", "mouse").put("dx", 0.0).put("dy", 0.0)
                    .put("buttons", 0).put("mode", "rel"))
            }
        }
        return true
    }
}
