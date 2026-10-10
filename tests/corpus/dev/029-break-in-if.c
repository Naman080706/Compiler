#include <stdio.h>

int main(void) {
    int balance = 120;
    int price = 150;
    if (price > balance) {
        printf("not enough money\n");
        break;
    }
    balance = balance - price;
    printf("balance left: %d\n", balance);
    return 0;
}
