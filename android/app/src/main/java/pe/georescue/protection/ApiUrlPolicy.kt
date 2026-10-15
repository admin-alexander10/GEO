package pe.georescue.protection

object ApiUrlPolicy {
    fun isAllowed(value: String, debugBuild: Boolean): Boolean =
        value.startsWith("https://") || (debugBuild && value.startsWith("http://"))
}
