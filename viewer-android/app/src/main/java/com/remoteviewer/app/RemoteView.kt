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

/**
 * Server ekranini chizadi va teginishlarni input hodisalariga aylantiradi.
 *
 * Ikki rejim:
 *  - touchscreen (standart): har bir barmoq `touch` kontakt sifatida yuboriladi — server
 *    haqiqiy multi-touch injekt qiladi, shuning uchun 2/3/4-barmoq gesturalar Windows'ning
 *    o'zida native ishlaydi (pinch/scroll/swipe).
 *  - touchpad: bitta barmoq nisbiy kursor harakati; tap = chap klик.
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

    private var lastX = 0f
    private var lastY = 0f

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

    override fun onTouchEvent(event: MotionEvent): Boolean {
        return if (touchpadMode) handleTouchpad(event) else handleTouchscreen(event)
    }

    private fun handleTouchscreen(event: MotionEvent): Boolean {
        val action = event.actionMasked
        val changed = event.actionIndex
        val contacts = JSONArray()
        for (i in 0 until event.pointerCount) {
            val state = when (action) {
                MotionEvent.ACTION_DOWN, MotionEvent.ACTION_POINTER_DOWN ->
                    if (i == changed) "down" else "move"
                MotionEvent.ACTION_UP, MotionEvent.ACTION_POINTER_UP ->
                    if (i == changed) "up" else "move"
                MotionEvent.ACTION_CANCEL -> "up"
                else -> "move"
            }
            val c = JSONObject()
            c.put("id", event.getPointerId(i))
            c.put("x", nx(event.getX(i)))
            c.put("y", ny(event.getY(i)))
            c.put("state", state)
            contacts.put(c)
        }
        val msg = JSONObject()
        msg.put("t", "touch")
        msg.put("contacts", contacts)
        onInput?.invoke(msg.toString())
        return true
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
                val m = JSONObject()
                m.put("t", "mouse")
                m.put("dx", dx.toDouble())
                m.put("dy", dy.toDouble())
                m.put("buttons", 0)
                m.put("mode", "rel")
                onInput?.invoke(m.toString())
            }
            MotionEvent.ACTION_UP -> {
                // tap -> chap klик (down + up)
                sendRelButton(1)
                sendRelButton(0)
            }
        }
        return true
    }

    private fun sendRelButton(buttons: Int) {
        val m = JSONObject()
        m.put("t", "mouse")
        m.put("dx", 0.0)
        m.put("dy", 0.0)
        m.put("buttons", buttons)
        m.put("mode", "rel")
        onInput?.invoke(m.toString())
    }
}
