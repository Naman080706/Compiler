#include <stdio.h>

int area(int w, int h);

int main(void) {
    int a = area(4, 5);
    printf("area = %d\n", a);
    return 0;
}

float area(int w, int h) {
    return w * h;
}
