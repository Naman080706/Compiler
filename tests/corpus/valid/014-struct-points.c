#include <stdio.h>

struct Point {
    int x;
    int y;
};

struct Point make_point(int x, int y) {
    struct Point p;
    p.x = x;
    p.y = y;
    return p;
}

int manhattan(struct Point a, struct Point b) {
    int dx = a.x - b.x;
    int dy = a.y - b.y;
    if (dx < 0) {
        dx = -dx;
    }
    if (dy < 0) {
        dy = -dy;
    }
    return dx + dy;
}

int main(void) {
    struct Point origin = {0, 0};
    struct Point far = make_point(3, -4);
    struct Point *ptr = &far;
    ptr->x += 1;
    printf("distance %d\n", manhattan(origin, far));
    return 0;
}
