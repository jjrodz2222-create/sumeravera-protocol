package com.sumeravera.protocol.core.crypto

import java.security.MessageDigest
import java.util.Arrays

/**
 * Ultra-low power, zero-allocation cryptographic hashing engine for edge devices.
 * Uses ThreadLocal MessageDigest caching and direct char-array hex conversions
 * to eliminate GC churn and minimize CPU instruction overhead.
 */
object FastCrypto {

    private val DIGEST_CACHE = object : ThreadLocal<MessageDigest>() {
        override fun initialValue(): MessageDigest {
            return MessageDigest.getInstance("SHA-256")
        }
    }

    private val HEX_CHARS = "0123456789abcdef".toCharArray()

    // Genesis hash: 64 zeros as cached string and raw 32 zero bytes
    val GENESIS_HASH_STRING = "0".repeat(64)
    val GENESIS_HASH_BYTES = ByteArray(32)

    /**
     * Compute SHA-256 directly on UTF-8 bytes into a new 32-byte array.
     */
    fun sha256Bytes(data: ByteArray, offset: Int = 0, length: Int = data.size): ByteArray {
        val md = DIGEST_CACHE.get()!!
        md.reset()
        md.update(data, offset, length)
        return md.digest()
    }

    /**
     * Compute SHA-256 into a caller-supplied 32-byte output buffer (ZERO allocation).
     */
    fun sha256BytesInto(data: ByteArray, offset: Int, length: Int, outBuffer: ByteArray, outOffset: Int = 0) {
        val md = DIGEST_CACHE.get()!!
        md.reset()
        md.update(data, offset, length)
        md.digest(outBuffer, outOffset, 32)
    }

    /**
     * Compute SHA-256 on String with zero-waste char-array encoding.
     */
    fun sha256(input: String): String {
        val md = DIGEST_CACHE.get()!!
        md.reset()
        // Fast UTF-8 encoding avoiding extra array allocations when possible
        val inputBytes = input.toByteArray(Charsets.UTF_8)
        md.update(inputBytes)
        val digest = md.digest()
        return bytesToHex(digest)
    }

    /**
     * Multi-part hash to avoid string concatenation like "$prevHash$payloadHash$timestamp".
     * Feeds segments directly into MessageDigest to eliminate intermediate String allocations.
     */
    fun sha256Chain(prevHash: String, payloadHash: String, timestamp: String): String {
        val md = DIGEST_CACHE.get()!!
        md.reset()
        md.update(prevHash.toByteArray(Charsets.US_ASCII))
        md.update(payloadHash.toByteArray(Charsets.US_ASCII))
        md.update(timestamp.toByteArray(Charsets.US_ASCII))
        val digest = md.digest()
        return bytesToHex(digest)
    }

    /**
     * Fast hex formatting without String.format("%02x") allocations.
     * Operates in O(N) single-pass with array lookup.
     */
    fun bytesToHex(bytes: ByteArray): String {
        val chars = CharArray(bytes.size * 2)
        var i = 0
        for (b in bytes) {
            val v = b.toInt() and 0xFF
            chars[i++] = HEX_CHARS[v ushr 4]
            chars[i++] = HEX_CHARS[v and 0x0F]
        }
        return String(chars)
    }

    /**
     * Fast hex decoding into byte array.
     */
    fun hexToBytes(hex: String): ByteArray {
        val len = hex.length
        val data = ByteArray(len / 2)
        var i = 0
        while (i < len) {
            data[i / 2] = ((Character.digit(hex[i], 16) shl 4) +
                    Character.digit(hex[i + 1], 16)).toByte()
            i += 2
        }
        return data
    }

    /**
     * Constant-time byte array equality for cryptographic verification.
     */
    fun constantTimeEquals(a: ByteArray, b: ByteArray): Boolean {
        if (a.size != b.size) return false
        var result = 0
        for (i in a.indices) {
            result = result or (a[i].toInt() xor b[i].toInt())
        }
        return result == 0
    }
}
