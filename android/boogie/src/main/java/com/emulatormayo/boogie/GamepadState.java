package com.emulatormayo.boogie;

/** Merge Android key and axis reports without releasing a still-held alias. */
final class GamepadState {
    private final boolean[] keys = new boolean[17];
    private final float[] motion = new float[17];
    final float[] axes = new float[4];
    void key(int index, boolean down) { keys[index] = down; }
    float button(int index) { return Math.max(keys[index] ? 1 : 0, motion[index]); }
    void motion(float x, float y, float rx, float ry, float hatX, float hatY, float left, float right) {
        axes[0] = bounded(x, -1, 1); axes[1] = bounded(y, -1, 1);
        axes[2] = bounded(rx, -1, 1); axes[3] = bounded(ry, -1, 1);
        motion[6] = bounded(left, 0, 1); motion[7] = bounded(right, 0, 1);
        motion[12] = hatY < -.5f ? 1 : 0; motion[13] = hatY > .5f ? 1 : 0;
        motion[14] = hatX < -.5f ? 1 : 0; motion[15] = hatX > .5f ? 1 : 0;
    }
    void clear() { java.util.Arrays.fill(keys, false); java.util.Arrays.fill(motion, 0); java.util.Arrays.fill(axes, 0); }
    private static float bounded(float value, float min, float max) { return Float.isFinite(value) ? Math.max(min, Math.min(max, value)) : 0; }
}
