// 원본 코드 (문제에서 제공된 그대로, 수정 없음). 리팩토링 대상 비교용.
@Test
fun testOrderFlow() {
    val shopItem = device.wait(Until.findObject(By.textContains("치킨")), 5000)
    shopItem.click()

    val menuItem = device.wait(Until.findObject(By.textContains("후라이드")), 3000)
    menuItem.click()

    val orderBtn = device.wait(Until.findObject(By.textContains("주문하기")), 3000)
    orderBtn.click()

    val payBtn = device.wait(Until.findObject(By.textContains("결제")), 3000)
    payBtn.click()

    Thread.sleep(5000)

    val statusText = device.wait(Until.findObject(By.textContains("접수 대기")), 3000)
    Assert.assertNotNull(statusText)
}
