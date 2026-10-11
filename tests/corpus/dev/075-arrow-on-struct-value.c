#include <stdio.h>

struct Box {
    int width;
    int height;
};

int main(void) {
    struct Box b = {3, 4};
    int area = b->width * b.height;
    printf("%d\n", area);
    return 0;
}
