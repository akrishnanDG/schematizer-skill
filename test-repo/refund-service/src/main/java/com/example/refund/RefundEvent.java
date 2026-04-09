package com.example.refund;

import com.fasterxml.jackson.annotation.JsonProperty;

public class RefundEvent {
    @JsonProperty("refund_id")
    private String refundId;

    @JsonProperty("order_id")
    private String orderId;

    @JsonProperty("customer_email")
    private String customerEmail;

    @JsonProperty("refund_amount")
    private double refundAmount;

    @JsonProperty("reason")
    private String reason;

    public RefundEvent() {}

    public String getRefundId() { return refundId; }
    public void setRefundId(String refundId) { this.refundId = refundId; }
    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }
    public String getCustomerEmail() { return customerEmail; }
    public void setCustomerEmail(String customerEmail) { this.customerEmail = customerEmail; }
    public double getRefundAmount() { return refundAmount; }
    public void setRefundAmount(double refundAmount) { this.refundAmount = refundAmount; }
    public String getReason() { return reason; }
    public void setReason(String reason) { this.reason = reason; }
}
