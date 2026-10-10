#include <stdio.h>

int main(void) {
    int price = 40;
    int qty = 3;
    int cost;
    cost = price * qty;
    printf("Cost: %d\n, cost);
    if (cost > 100) {
        printf("expensive\n");
    }
    cost = cost + 5;
    printf("with tax %d\n", cost);
    return 0;
}
