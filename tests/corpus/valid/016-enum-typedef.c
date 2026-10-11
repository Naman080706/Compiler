#include <stdio.h>

enum Color { RED, GREEN = 5, BLUE };

typedef struct {
    int id;
    enum Color color;
} Item;

typedef unsigned int Count;

const char *color_name(enum Color c) {
    switch (c) {
        case RED:
            return "red";
        case GREEN:
            return "green";
        default:
            return "blue";
    }
}

int main(void) {
    Item items[2];
    Count n = 2;
    Count i;
    items[0].id = 1;
    items[0].color = GREEN;
    items[1].id = 2;
    items[1].color = BLUE;
    for (i = 0; i < n; i++) {
        printf("%d is %s (%d)\n", items[i].id, color_name(items[i].color), items[i].color);
    }
    return 0;
}
